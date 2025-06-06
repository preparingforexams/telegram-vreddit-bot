import logging
import tempfile

from cancer import telegram
from cancer.command.util import initialize_subscriber
from cancer.config import Config
from cancer.message import Topic, VoiceMessage
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)


async def _handle_payload(payload: VoiceMessage) -> Subscriber.Result:
    _LOG.info("Received payload: %s", payload)

    if payload.file_size > 20_000_000:
        _LOG.info("Skipping because file is too large")
        return Subscriber.Result.Ack

    with tempfile.TemporaryFile() as file:
        await telegram.download_file(payload.file_id, file)

        _LOG.info("Downloaded file of size %d", file.tell())

        file.seek(0)

        await telegram.send_audio_message(
            chat_id=payload.chat_id,
            reply_to_message_id=payload.message_id,
            audio=file,
            name=f"voice-{payload.file_id}",
        )

    return Subscriber.Result.Ack


async def run(config: Config) -> None:
    telegram.init(config.telegram)

    topic = Topic.voiceDownload
    _LOG.debug("Subscribing to topic %s", topic)

    subscriber = await initialize_subscriber(config.event)

    await subscriber.subscribe(
        topic,
        VoiceMessage,
        _handle_payload,
    )
