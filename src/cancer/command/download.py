import asyncio
import logging
import sys
import uuid
from asyncio.locks import Lock
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from httpx import AsyncClient
from PIL import Image
from telegram import Bot, ReplyParameters, Video
from telegram.error import BadRequest, NetworkError, TelegramError
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError, UnsupportedError

from cancer.command.util import initialize_subscriber
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

    size: int | None
    if info is None:
        size = None
        thumbnails = []
    else:
        size = cast(
            int | None,
            info.get("filesize") or info.get("filesize_approx"),
        )

        if size is None:
            _LOG.debug("Got no file size for URL %s", url)
        else:
            _LOG.debug(
                "Got a file size of approx. %d MB for URL %s",
                round(float(size) / 1_000_000),
                url,
            )

        raw_thumbnails = cast(list, info.get("thumbnails", []))
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

    ytdl = YoutubeDL(params=params)  # type: ignore[arg-type]

    try:
        return_code = ytdl.download([url])  # type: ignore[func-returns-value]
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

    cure_names = list(Path.iterdir(cure_dir))
    _LOG.info("Downloaded files %s", cure_names)

    return cure_names


def _get_dimensions(image_path: Path) -> tuple[int, int]:
    image = Image.open(image_path)
    return image.size


class _Downloader:
    def __init__(self, bot: Bot, config: DownloaderConfig) -> None:
        self.bot = bot
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
        cure_path: Path | None = None,
        retries: int = 2,
    ) -> Path | None:
        _LOG.info(
            "Uploading video %s (%d retries left)",
            video_file,
            retries,
        )

        if cure_path is None:
            cure_path = await self._ensure_compatibility(video_file)
        else:
            _LOG.info("Skipping compatibility check because we already have a cure")

        if not cure_path:
            _LOG.info("Not uploading incompatible file %s", video_file)
            return None

        try:
            message = await self.bot.send_video(
                chat_id,
                cure_path,
                reply_parameters=ReplyParameters(
                    message_id,
                )
                if message_id
                else None,
                thumbnail=thumb_path,
            )
        except NetworkError as e:
            if retries > 0:
                _LOG.warning("Video upload failed due to network issue. Retrying...")
                return await self._upload_video(
                    chat_id,
                    message_id,
                    thumb_path,
                    video_file,
                    cure_path,
                    retries - 1,
                )

            _LOG.error(
                "Video failed due to network multiple times. Requeueing...",
                exc_info=e,
            )
            raise TryAgainException from e
        except TelegramError as e:
            _LOG.error(
                "Could not upload video (entity too large?)."
                " Initial size: %d, cured: %d",
                video_file.stat().st_size,
                cure_path.stat().st_size,
                exc_info=e,
            )
            return None

        video = cast(Video, message.video)
        file_id = video.file_id
        return Path(file_id)

    async def _notify_failure(
        self,
        *,
        chat_id: int,
        message_id: int,
        reaction: str,
        private_chat_message: str | None = None,
    ) -> None:
        try:
            await self.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=reaction,
            )
            if private_chat_message and chat_id > 0:
                # private chat
                await self.bot.send_message(
                    chat_id=chat_id,
                    reply_parameters=ReplyParameters(
                        message_id,
                    ),
                    text=private_chat_message,
                )
        except BadRequest:
            _LOG.warning("Could not set reaction on message (probably deleted)")

    async def handle_payload(
        self,
        payload: DownloadMessage,
        attempt: int,
    ) -> Subscriber.Result:
        _LOG.info("Received payload: %s", payload)

        client = AsyncClient(timeout=60)

        with TemporaryDirectory(dir=str(self.config.storage_dir)) as folder_path:
            folder = Path(folder_path)
            async with _busy_lock:
                found_too_large = False
                files: list[tuple[Path | None, Path]] = []
                for url in payload.urls:
                    info = await _run_blocking(lambda: _get_info(url))
                    if info.size is not None and info.size > self.config.max_file_size:
                        _LOG.info("Skipping URL %s because it's too large", url)
                        found_too_large = True
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
                        if attempt < 6:
                            _LOG.warning("Got exception during download", exc_info=e)
                            return Subscriber.Result.Requeue

                        _LOG.error(
                            "Want to requeue, but maximum number of attempts reached. Dropping message.",
                            exc_info=e,
                        )
                        return Subscriber.Result.Drop
                    except AccessDeniedException as e:
                        _LOG.error("Was denied access to service", exc_info=e)
                        return Subscriber.Result.Requeue

                    for file in download_result:
                        files.append((thumb_file, file))

                if not files:
                    _LOG.warning("Download returned no videos")
                    if found_too_large:
                        reaction = "🐳"
                        private_message = (
                            "Das Video ist zu groß für die Telegram Bot API"
                        )
                    else:
                        reaction = "🗿"
                        private_message = "Konnte keine Videos finden"

                    await self._notify_failure(
                        chat_id=payload.chat_id,
                        message_id=payload.message_id,
                        reaction=reaction,
                        private_chat_message=private_message,
                    )
                    return Subscriber.Result.Ack

                for thumb_file, file in files:
                    await self._upload_video(
                        payload.chat_id, payload.message_id, thumb_file, file
                    )

                _LOG.info("Successfully handled payload")
                return Subscriber.Result.Ack


async def run(config: Config) -> None:
    downloader_config = config.download
    if downloader_config is None:
        _LOG.error("No downloader config found")
        sys.exit(1)

    storage_dir = downloader_config.storage_dir
    if not storage_dir.exists():
        storage_dir.mkdir()

    topic = downloader_config.topic
    _LOG.debug("Subscribing to topic %s", topic)
    subscriber = await initialize_subscriber(config.event)
    downloader = _Downloader(Bot(config.telegram.token), downloader_config)

    await subscriber.subscribe(topic, DownloadMessage, downloader.handle_payload)
