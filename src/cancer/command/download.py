import logging
import os
import signal
import subprocess
import sys
import uuid
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from threading import Lock
from typing import List, Optional

import requests
from PIL import Image
from yt_dlp import YoutubeDL
from yt_dlp.utils import UnsupportedError, DownloadError

from cancer import telegram
from cancer.adapter.rabbit import RabbitConfig, RabbitSubscriber
from cancer.message import DownloadMessage, Topic
from cancer.port.subscriber import Subscriber

_STORAGE_DIR = os.getenv("STORAGE_DIR", "downloads")
_UPLOAD_CHAT = os.getenv("UPLOAD_CHAT_ID", "1259947317")
_MAX_FILE_SIZE = int(os.getenv("MAX_DOWNLOAD_FILE_SIZE", "40_000_000"))

_LOG = logging.getLogger(__name__)

_busy_lock = Lock()


@dataclass
class VideoInfo:
    size: Optional[int]
    thumbnails: List[str]


def _get_info(url: str) -> VideoInfo:
    ytdl = YoutubeDL()

    try:
        info = ytdl.extract_info(url, download=False)
    except DownloadError:
        return VideoInfo(None, [])

    size = info.get("filesize") or info.get("filesize_approx")
    if size is None:
        _LOG.debug("Got no file size for URL %s", url)
    else:
        _LOG.debug(
            "Got a file size of approx. %d MB for URL %s",
            round(float(size) / 1_000_000),
            url,
        )

    raw_thumbnails = info.get("thumbnails", [])
    thumbnails = [
        t["url"]
        for t in sorted(raw_thumbnails, key=lambda t: t["preference"], reverse=True)
    ]

    return VideoInfo(size, thumbnails)


def _download_videos(base_folder: str, url: str) -> List[str]:
    cure_id = str(uuid.uuid4())
    cure_dir = os.path.join(base_folder, cure_id)
    os.mkdir(cure_dir)

    ytdl = YoutubeDL(params={
        "outtmpl": f"{cure_dir}/output%(autonumber)d.%(ext)s",
    })

    try:
        return_code = ytdl.download([url])
    except DownloadError as e:
        if e.exc_info is UnsupportedError:
            _LOG.warning("Download URL unsupported by youtube-dl: %s", url, exc_info=e)
            return []

        _LOG.error("Downloading failed for URL %s", url, exc_info=e)
        return []
    if return_code != 0:
        _LOG.error("YTDL returned error code %d", return_code)
        return []

    cure_names = os.listdir(cure_dir)
    _LOG.debug("Downloaded files %s", cure_names)

    return [
        os.path.join(cure_dir, cure_name)
        for cure_name in cure_names
    ]


def _convert_cure(input_path: str, output_path: str):
    _LOG.info("Converting from %s to %s", input_path, output_path)
    process = subprocess.Popen([
        'ffmpeg',
        '-i', input_path,
        output_path,
    ])
    if process.wait() != 0:
        raise RuntimeError("Could not convert file!")


def _ensure_compatibility(original_path: str) -> str:
    base, ext = os.path.splitext(original_path)
    if ext == ".mp4":
        return original_path

    converted_path = f"{base}.mp4"
    _convert_cure(original_path, converted_path)
    return converted_path


def _max_dimension(image_path: str) -> int:
    image = Image.open(image_path)
    return max(image.size)


def _download_thumb(cure_dir: str, urls: List[str]) -> Optional[str]:
    for url in urls:
        if not url.endswith(".jpg"):
            continue

        try:
            response = requests.get(url)
            response.raise_for_status()
        except Exception as e:
            _LOG.error("Could not download thumbnail %s", url, exc_info=e)
            continue
        else:
            # TODO: maybe don't download the whole content here
            if len(response.content) > 200_000:
                _LOG.info("Skipping thumbnail %s because its file size is too large", url)
                continue

            _LOG.debug("Found thumbnail with size %d", len(response.content))

            thumb_path = os.path.join(cure_dir, 'thumb.jpg')
            with open(thumb_path, 'wb') as f:
                f.write(response.content)

            if _max_dimension(thumb_path) > 320:
                _LOG.info("Skipping thumbnail %s because its dimensions are too large", url)
                continue

            return thumb_path


def _upload_video(thumb_path: Optional[str], video_file: str) -> Optional[str]:
    cure_path = _ensure_compatibility(video_file)
    try:
        message = telegram.upload_video(_UPLOAD_CHAT, cure_path, thumb_path=thumb_path)
    except requests.exceptions.HTTPError as e:
        response: Optional[requests.Response] = e.response
        if response and response.status_code == 413:
            _LOG.error(
                "Could not upload video (entity too large). Initial size: %d, cured: %d",
                os.path.getsize(video_file),
                os.path.getsize(cure_path),
                exc_info=e,
            )
            return None
        else:
            _LOG.warning("Re-raising exception with response %s", response)
            if response:
                _LOG.warning("Response status: %d", response.status_code)
            raise e

    video = message["video"]
    file_id = video["file_id"]
    return file_id


def _handle_payload(payload: DownloadMessage) -> Subscriber.Result:
    _LOG.info("Received payload: %s", payload)

    with TemporaryDirectory(dir=_STORAGE_DIR) as folder:
        with _busy_lock:
            files = []
            for url in payload.urls:
                info = _get_info(url)
                if info.size is not None and info.size > _MAX_FILE_SIZE:
                    _LOG.info("Skipping URL %s because it's too large", url)
                    continue

                thumb_file: Optional[str] = None
                if info.thumbnails:
                    _LOG.debug(
                        "Found %d thumbnail candidates for URL %s",
                        len(info.thumbnails),
                        url,
                    )
                    thumb_file = _download_thumb(folder, info.thumbnails)

                for file in _download_videos(folder, url):
                    files.append((thumb_file, file))

            if not files:
                _LOG.warning("Download returned no videos")
                return Subscriber.Result.Ack

            video_ids = [_upload_video(thumb_file, file) for thumb_file, file in files]

            telegram.send_video_group(
                chat_id=payload.chat_id,
                reply_to_message_id=payload.message_id,
                videos=[video_id for video_id in video_ids if video_id is not None],
            )

            _LOG.info("Successfully handled payload")
            return Subscriber.Result.Ack


def run():
    telegram.check()

    if not os.path.exists(_STORAGE_DIR):
        os.mkdir(_STORAGE_DIR)

    signal.signal(signal.SIGTERM, lambda _: sys.exit(0))

    download_type = os.getenv("DOWNLOAD_TYPE")
    if download_type == "insta":
        topic = Topic.instaDownload
    elif download_type == "youtube":
        topic = Topic.youtubeDownload
    elif download_type == "tiktok":
        topic = Topic.tiktokDownload
    else:
        topic = Topic.download

    _LOG.debug("Subscribing to topic %s", topic)
    subscriber: Subscriber = RabbitSubscriber(RabbitConfig.from_env())

    # readiness_server = ReadinessServer()
    # readiness_server.start(lambda: not _busy_lock.locked())
    subscriber.subscribe(topic, DownloadMessage, _handle_payload)
