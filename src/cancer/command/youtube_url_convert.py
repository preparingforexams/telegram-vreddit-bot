import logging
import signal
import sys
from urllib.parse import urlparse

from cancer import telegram
from cancer.adapter.rabbit import RabbitSubscriber, RabbitConfig
from cancer.message import Topic
from cancer.message.youtube_url_convert import YoutubeUrlConvertMessage
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)


def _rewrite_youtube_url(case: str) -> str:
    parsed = urlparse(case)
    video_id = parsed.path.split("/")[-1]
    return f"https://youtube.com/watch?v={video_id}"


def _handle_payload(payload: YoutubeUrlConvertMessage) -> Subscriber.Result:
    _LOG.info("Received payload: %s", payload)

    rewritten_urls = [_rewrite_youtube_url(url) for url in payload.urls]
    url_list_text = "\n".join(rewritten_urls)
    text = f"I cured that cancer of yours:\n{url_list_text}"
    telegram.send_message(
        chat_id=payload.chat_id,
        reply_to_message_id=payload.message_id,
        text=text,
    )

    return Subscriber.Result.Ack


def run():
    telegram.check()

    signal.signal(signal.SIGTERM, lambda _: sys.exit(0))

    topic = Topic.youtubeUrlConvert
    _LOG.debug("Subscribing to topic %s", topic)

    subscriber: Subscriber = RabbitSubscriber(RabbitConfig.from_env())
    subscriber.subscribe(
        topic,
        YoutubeUrlConvertMessage,
        _handle_payload,
    )
