import logging
import os
import signal
import subprocess
import sys
import uuid
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from threading import Lock
from typing import List, Optional, Tuple, Union

from httpx import Client, HTTPStatusError, Response
from PIL import Image
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError, UnsupportedError

from cancer import telegram
from cancer.adapter.pubsub import PubSubConfig, PubSubSubscriber
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
    if raw_thumbnails:
        _LOG.debug(
            "Thumbnails for URL %s have the following keys: %s",
            url,
            list(raw_thumbnails[0].keys()),
        )
    thumbnails = [
        t["url"]
        for t in sorted(
            raw_thumbnails,
            key=lambda t: t.get("preference") or t.get("filesize") or -999999,
            reverse=True,
        )
    ]

    return VideoInfo(size, thumbnails)


class AccessDeniedException(Exception):
    pass


class TryAgainException(Exception):
    pass


def _download_videos(base_folder: str, url: str) -> List[str]:
    cure_id = str(uuid.uuid4())
    cure_dir = os.path.join(base_folder, cure_id)
    os.mkdir(cure_dir)

    params = {
        "outtmpl": f"{cure_dir}/output%(autonumber)d.%(ext)s",
    }

    if (username := os.getenv("USERNAME")) and (password := os.getenv("PASSWORD")):
        params["username"] = username
        params["password"] = password

    ytdl = YoutubeDL(params=params)

    try:
        return_code = ytdl.download([url])
    except DownloadError as e:
        cause = e.exc_info
        if isinstance(cause, UnsupportedError):
            _LOG.warning("Download URL unsupported by youtube-dl: %s", url, exc_info=e)
            return []

        if isinstance(cause, ExtractorError):
            if (
                cause.msg == "There's no video in this tweet."
                and not cause.expected
                and not cause.video_id
            ):
                _LOG.info("YouTubeDL did not find any videos at %s", url)
                return []

            if "rate-limit reached or login required" in cause.msg:
                raise AccessDeniedException(
                    f"Maybe we should include login data for {url}"
                ) from e

        raise TryAgainException from e
    if return_code != 0:
        _LOG.error("YTDL returned error code %d", return_code)
        return []

    cure_names = os.listdir(cure_dir)
    _LOG.debug("Downloaded files %s", cure_names)

    return [os.path.join(cure_dir, cure_name) for cure_name in cure_names]


def _convert_cure(input_path: str, output_path: str):
    _LOG.info("Converting from %s to %s", input_path, output_path)
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-i",
            input_path,
            output_path,
        ]
    )
    if process.wait() != 0:
        raise RuntimeError("Could not convert file!")


def _ensure_compatibility(original_path: str) -> str | None:
    base, ext = os.path.splitext(original_path)
    if ext == ".mp4":
        return original_path

    if ext in [".png", ".jpg"]:
        return None

    converted_path = f"{base}.mp4"
    _convert_cure(original_path, converted_path)
    return converted_path


def _get_dimensions(image_path: str) -> Tuple[int, int]:
    image = Image.open(image_path)
    return image.size


def _download_thumb(client: Client, cure_dir: str, urls: List[str]) -> Optional[str]:
    for url in urls:
        if not url.endswith(".jpg"):
            continue

        try:
            response = client.get(url)
            response.raise_for_status()
        except Exception as e:
            _LOG.warning("Could not download thumbnail %s", url, exc_info=e)
            continue
        else:
            # TODO: maybe don't download the whole content here
            if len(response.content) > 200_000:
                _LOG.info(
                    "Skipping thumbnail %s because its file size is too large", url
                )
                continue

            _LOG.debug("Found thumbnail with size %d", len(response.content))

            thumb_path = os.path.join(cure_dir, "thumb.jpg")
            with open(thumb_path, "wb") as f:
                f.write(response.content)

            dimensions = _get_dimensions(thumb_path)
            if max(dimensions) > 320:
                _LOG.info(
                    "Skipping thumbnail %s because its"
                    " dimensions (%d x %d) are too large",
                    url,
                    dimensions[0],
                    dimensions[1],
                )
                continue
            else:
                _LOG.debug(
                    "Using thumbnail %s with dimensions %d x %d and size %d",
                    url,
                    dimensions[0],
                    dimensions[1],
                    os.path.getsize(thumb_path),
                )

            return thumb_path
    return None


def _upload_video(
    chat_id: Union[str, int],
    message_id: Optional[int],
    thumb_path: Optional[str],
    video_file: str,
) -> Optional[str]:
    cure_path = _ensure_compatibility(video_file)

    if not cure_path:
        _LOG.info("Not uploading incompatible file %s", video_file)
        return None

    try:
        message = telegram.upload_video(
            chat_id,
            cure_path,
            reply_to_message_id=message_id,
            thumb_path=thumb_path,
        )
    except HTTPStatusError as e:
        response: Response = e.response
        if response.status_code == 413:
            _LOG.error(
                "Could not upload video (entity too large)."
                " Initial size: %d, cured: %d",
                os.path.getsize(video_file),
                os.path.getsize(cure_path),
                exc_info=e,
            )
            return None
        else:
            _LOG.warning("Re-raising exception with response %s", response)
            raise e

    video = message["video"]
    file_id = video["file_id"]
    return file_id


def _handle_payload(payload: DownloadMessage) -> Subscriber.Result:
    _LOG.info("Received payload: %s", payload)

    client = Client(timeout=60)

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
                    thumb_file = _download_thumb(client, folder, info.thumbnails)

                try:
                    download_result = _download_videos(folder, url)
                except TryAgainException as e:
                    _LOG.warning("Got exception during download", exc_info=e)
                    return Subscriber.Result.Requeue
                except AccessDeniedException as e:
                    _LOG.error("Was denied access to service", exc_info=e)
                    return Subscriber.Result.Requeue

                for file in download_result:
                    files.append((thumb_file, file))

            if not files:
                _LOG.warning("Download returned no videos")
                return Subscriber.Result.Ack

            for thumb_file, file in files:
                _upload_video(payload.chat_id, payload.message_id, thumb_file, file)

            _LOG.info("Successfully handled payload")
            return Subscriber.Result.Ack


def run() -> None:
    telegram.check()

    if not os.path.exists(_STORAGE_DIR):
        os.mkdir(_STORAGE_DIR)

    signal.signal(signal.SIGTERM, lambda _, __: sys.exit(0))

    topic: Topic
    match os.getenv("DOWNLOAD_TYPE"):
        case "insta":
            topic = Topic.instaDownload
        case "youtube":
            topic = Topic.youtubeDownload
        case "tiktok":
            topic = Topic.tiktokDownload
        case "twitter":
            topic = Topic.twitterDownload
        case "vimeo":
            topic = Topic.vimeoDownload
        case download_type:
            _LOG.info(
                "Using generic download topic for download type %s", download_type
            )
            topic = Topic.download

    _LOG.debug("Subscribing to topic %s", topic)
    subscriber: Subscriber = PubSubSubscriber(PubSubConfig.from_env())

    # readiness_server = ReadinessServer()
    # readiness_server.start(lambda: not _busy_lock.locked())
    subscriber.subscribe(topic, DownloadMessage, _handle_payload)
