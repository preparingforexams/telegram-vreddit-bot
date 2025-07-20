import logging
import tempfile
from pathlib import Path

from telegram import Bot
from telegram.constants import FileSizeLimit

from cancer.command.util import initialize_subscriber
from cancer.config import Config
from cancer.message import Topic, VoiceMessage
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)


class _TelegramAudioConverter:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def handle_payload(self, payload: VoiceMessage) -> Subscriber.Result:
        _LOG.info("Received payload: %s", payload)

        if payload.file_size > FileSizeLimit.FILESIZE_DOWNLOAD:
            _LOG.info("Skipping because file is too large")
            return Subscriber.Result.Ack

        with tempfile.TemporaryDirectory() as directory:
            tg_file = await self.bot.get_file(payload.file_id)
            filename = tg_file.file_path or f"voice-{payload.file_id}.ogg"
            file_path = Path(directory) / filename
            await tg_file.download_to_drive(file_path)

            _LOG.info("Downloaded file of size %d", tg_file.file_size)

            await self.bot.send_audio(
                chat_id=payload.chat_id,
                reply_to_message_id=payload.message_id,
                audio=file_path,
                filename=filename,
            )

        return Subscriber.Result.Ack


async def run(config: Config) -> None:
    topic = Topic.voiceDownload
    _LOG.debug("Subscribing to topic %s", topic)

    subscriber = await initialize_subscriber(config.event)
    converter = _TelegramAudioConverter(Bot(config.telegram.token))

    await subscriber.subscribe(
        topic,
        VoiceMessage,
        converter.handle_payload,
    )
