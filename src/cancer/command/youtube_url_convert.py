import logging
import signal
import sys
from urllib.parse import urlparse

from cancer import telegram
from cancer.adapter.publisher_pubsub import PubSubSubscriber
from cancer.config import Config
from cancer.message import Topic
from cancer.message.youtube_url_convert import YoutubeUrlConvertMessage
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)


def _rewrite_youtube_url(case: str) -> str:
    parsed = urlparse(case)
    video_id = parsed.path.split("/")[-1]
    return f"https://youtube.com/watch?v={video_id}"


async def _handle_payload(payload: YoutubeUrlConvertMessage) -> Subscriber.Result:
    _LOG.info("Received payload: %s", payload)

    rewritten_urls = [_rewrite_youtube_url(url) for url in payload.urls]
    url_list_text = "\n".join(rewritten_urls)
    await telegram.send_message(
        chat_id=payload.chat_id,
        reply_to_message_id=payload.message_id,
        text=url_list_text,
    )

    return Subscriber.Result.Ack


async def run(config: Config) -> None:
    telegram.init(config.telegram)

    signal.signal(signal.SIGTERM, lambda _, __: sys.exit(0))

    topic = Topic.youtubeUrlConvert
    _LOG.debug("Subscribing to topic %s", topic)

    pubsub_config = config.event.pub_sub
    if pubsub_config is None:
        _LOG.error("No pubsub config found")
        sys.exit(1)
    subscriber: Subscriber = PubSubSubscriber(pubsub_config)
    await subscriber.subscribe(
        topic,
        YoutubeUrlConvertMessage,
        _handle_payload,
    )
