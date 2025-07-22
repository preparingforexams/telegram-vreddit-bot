import logging
from urllib.parse import urlparse

from telegram import Bot, ReplyParameters

from cancer.command.util import initialize_subscriber
from cancer.config import Config
from cancer.message import Topic
from cancer.message.youtube_url_convert import YoutubeUrlConvertMessage
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)


def _rewrite_youtube_url(case: str) -> str:
    parsed = urlparse(case)
    video_id = parsed.path.split("/")[-1]
    return f"https://youtube.com/watch?v={video_id}"


class _YouTubeUrlConverter:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def handle_payload(
        self,
        payload: YoutubeUrlConvertMessage,
        _: int,
    ) -> Subscriber.Result:
        _LOG.info("Received payload: %s", payload)

        rewritten_urls = [_rewrite_youtube_url(url) for url in payload.urls]
        url_list_text = "\n".join(rewritten_urls)
        await self.bot.send_message(
            chat_id=payload.chat_id,
            reply_parameters=ReplyParameters(
                payload.message_id,
            ),
            text=url_list_text,
        )

        return Subscriber.Result.Ack


async def run(config: Config) -> None:
    topic = Topic.youtubeUrlConvert
    _LOG.debug("Subscribing to topic %s", topic)

    subscriber = await initialize_subscriber(config.event)
    converter = _YouTubeUrlConverter(Bot(config.telegram.token))

    await subscriber.subscribe(
        topic,
        YoutubeUrlConvertMessage,
        converter.handle_payload,
    )
