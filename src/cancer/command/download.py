import asyncio
import logging
import signal
import sys
import uuid
from asyncio.locks import Lock
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from httpx import AsyncClient, HTTPStatusError, Response
from PIL import Image
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError, UnsupportedError

from cancer import telegram
from cancer.adapter.publisher_pubsub import PubSubSubscriber
from cancer.config import Config, DownloaderConfig, DownloaderCredentials
from cancer.message import DownloadMessage
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)

_busy_lock = Lock()


@dataclass
class VideoInfo:
    size: int | None
    thumbnails: list[str]


async def _run_blocking[T](func: Callable[[], T]) -> T:
    return await asyncio.get_running_loop().run_in_executor(None, func)


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


def _download_videos(
    base_folder: Path,
    credentials: DownloaderCredentials,
    url: str,
) -> list[Path]:
    cure_id = str(uuid.uuid4())
    cure_dir = base_folder / cure_id
    cure_dir.mkdir()

    params = {
        "outtmpl": f"{cure_dir}/output%(autonumber)d.%(ext)s",
    }

    if (username := credentials.username) and (password := credentials.password):
        params["username"] = username
        params["password"] = password

    if cookie_file := credentials.cookie_file:
        params["cookies"] = cookie_file

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

    cure_names = Path.iterdir(cure_dir)
    _LOG.debug("Downloaded files %s", cure_names)

    return list(cure_names)


def _get_dimensions(image_path: Path) -> tuple[int, int]:
    image = Image.open(image_path)
    return image.size


class _Downloader:
    def __init__(self, config: DownloaderConfig) -> None:
        self.config = config

    async def _convert_cure(self, input_path: Path, output_path: Path) -> None:
        _LOG.info("Converting from %s to %s", input_path, output_path)
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i",
            input_path,
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if await process.wait() != 0:
            if (stdout := process.stdout) is not None:
                output = (await stdout.read()).decode("utf-8")
            else:
                output = ""

            if (stderr := process.stderr) is not None:
                error_output = (await stderr.read()).decode("utf-8")
            else:
                error_output = ""

            raise RuntimeError(
                f"Could not convert file! Output:\n{output}\n\nStderr: {error_output}"
            )

    async def _ensure_compatibility(self, original_path: Path) -> Path | None:
        ext = original_path.suffix
        if ext == ".mp4":
            return original_path

        if ext in [".png", ".jpg"]:
            return None

        converted_path = original_path.with_suffix(".mp4")
        await self._convert_cure(original_path, converted_path)
        return converted_path

    async def _download_thumb(
        self, client: AsyncClient, cure_dir: Path, urls: list[str]
    ) -> Path | None:
        for url in urls:
            if not url.endswith(".jpg"):
                continue

            try:
                response = await client.get(url)
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

                thumb_path = cure_dir / "thumb.jpg"
                with thumb_path.open("wb") as f:
                    f.write(response.content)

                dimensions = await _run_blocking(lambda: _get_dimensions(thumb_path))
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
                        thumb_path.stat().st_size,
                    )

                return thumb_path
        return None

    async def _upload_video(
        self,
        chat_id: str | int,
        message_id: int | None,
        thumb_path: Path | None,
        video_file: Path,
    ) -> Path | None:
        cure_path = await self._ensure_compatibility(video_file)

        if not cure_path:
            _LOG.info("Not uploading incompatible file %s", video_file)
            return None

        try:
            message = await telegram.upload_video(
                chat_id,
                cure_path,
                reply_to_message_id=message_id,
                thumb_path=thumb_path,
            )
        except HTTPStatusError as e:
            response: Response = e.response
            if response.status_code == 413:
                _LOG.warning(
                    "Could not upload video (entity too large)."
                    " Initial size: %d, cured: %d",
                    video_file.stat().st_size,
                    cure_path.stat().st_size,
                    exc_info=e,
                )
                return None
            else:
                _LOG.warning("Re-raising exception with response %s", response)
                raise e

        video = message["video"]
        file_id = video["file_id"]
        return file_id

    async def handle_payload(
        self,
        payload: DownloadMessage,
    ) -> Subscriber.Result:
        _LOG.info("Received payload: %s", payload)

        client = AsyncClient(timeout=60)

        with TemporaryDirectory(dir=str(self.config.storage_dir)) as folder_path:
            folder = Path(folder_path)
            async with _busy_lock:
                files: list[tuple[Path | None, Path]] = []
                for url in payload.urls:
                    info = await _run_blocking(lambda: _get_info(url))
                    if info.size is not None and info.size > self.config.max_file_size:
                        _LOG.info("Skipping URL %s because it's too large", url)
                        continue

                    thumb_file: Path | None = None
                    if info.thumbnails:
                        _LOG.debug(
                            "Found %d thumbnail candidates for URL %s",
                            len(info.thumbnails),
                            url,
                        )
                        thumb_file = await self._download_thumb(
                            client, folder, info.thumbnails
                        )

                    try:
                        download_result = await _run_blocking(
                            lambda: _download_videos(
                                folder,
                                self.config.credentials,
                                url,
                            )
                        )
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
                    await self._upload_video(
                        payload.chat_id, payload.message_id, thumb_file, file
                    )

                _LOG.info("Successfully handled payload")
                return Subscriber.Result.Ack


async def run(config: Config) -> None:
    telegram.init(config.telegram)

    downloader_config = config.download
    if downloader_config is None:
        _LOG.error("No downloader config found")
        sys.exit(1)

    pubsub_config = config.event.pub_sub
    if pubsub_config is None:
        _LOG.error("No pubsub config found")
        sys.exit(1)

    storage_dir = downloader_config.storage_dir
    if not storage_dir.exists():
        storage_dir.mkdir()

    signal.signal(signal.SIGTERM, lambda _, __: sys.exit(0))

    topic = downloader_config.topic
    _LOG.debug("Subscribing to topic %s", topic)
    subscriber: Subscriber = PubSubSubscriber(pubsub_config)
    downloader = _Downloader(downloader_config)

    await subscriber.subscribe(topic, DownloadMessage, downloader.handle_payload)
