import logging
import signal
import sys

from cancer import telegram
from cancer.adapter.pubsub import PubSubSubscriber, PubSubConfig
from cancer.message import Topic, VoiceMessage
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)


def _handle_payload(payload: VoiceMessage) -> Subscriber.Result:
    _LOG.info("Received payload: %s", payload)
    telegram.send_audio_message(
        chat_id=payload.chat_id,
        reply_to_message_id=payload.message_id,
        audio=payload.file_id,
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
