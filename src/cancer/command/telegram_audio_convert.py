import logging
import signal
import sys
import tempfile

from cancer import telegram
from cancer.adapter.publisher_pubsub import PubSubConfig, PubSubSubscriber
from cancer.message import Topic, VoiceMessage
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)


def _handle_payload(payload: VoiceMessage) -> Subscriber.Result:
    _LOG.info("Received payload: %s", payload)

    if payload.file_size > 20_000_000:
        _LOG.info("Skipping because file is too large")
        return Subscriber.Result.Ack

    with tempfile.TemporaryFile() as file:
        telegram.download_file(payload.file_id, file)

        _LOG.info("Downloaded file of size %d", file.tell())

        file.seek(0)

        telegram.send_audio_message(
            chat_id=payload.chat_id,
            reply_to_message_id=payload.message_id,
            audio=file,
            name=f"voice-{payload.file_id}",
        )

    return Subscriber.Result.Ack


def run() -> None:
    telegram.check()

    signal.signal(signal.SIGTERM, lambda _, __: sys.exit(0))

    topic = Topic.voiceDownload
    _LOG.debug("Subscribing to topic %s", topic)

    subscriber: Subscriber = PubSubSubscriber(PubSubConfig.from_env())
    subscriber.subscribe(
        topic,
        VoiceMessage,
        _handle_payload,
    )
