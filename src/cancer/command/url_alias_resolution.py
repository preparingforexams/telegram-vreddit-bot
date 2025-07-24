import asyncio
import logging

import httpx
from telegram import Bot, ReplyParameters

from cancer.command.util import initialize_subscriber
from cancer.config import Config
from cancer.message import Topic
from cancer.message.youtube_url_convert import UrlConvertMessage
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)


async def _resolve_url(client: httpx.AsyncClient, url: str) -> str | None:
    request = client.build_request("GET", url)
    current_url = url
    while request is not None:
        current_url = str(request.url)
        _LOG.info("Resolving URL %s", current_url)
        try:
            response = await client.send(request)
        except httpx.RequestError as e:
            _LOG.error("Could not resolve URL %s", url, exc_info=e)
            return None

        if response.is_error:
            _LOG.error("Error response for URL %s", url)
            return None

        request = response.next_request

    return current_url


class _UrlAliasResolver:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def handle_payload(
        self,
        payload: UrlConvertMessage,
        _: int,
    ) -> Subscriber.Result:
        _LOG.info("Received payload: %s", payload)

        resolve_tasks: list[asyncio.Task[str | None]] = []
        async with httpx.AsyncClient() as client:
            async with asyncio.TaskGroup() as tg:
                for url in payload.urls:
                    task = tg.create_task(_resolve_url(client, url))
                    resolve_tasks.append(task)

        resolved_urls = [t.result() for t in resolve_tasks]
        url_list_text = "\n".join(url for url in resolved_urls if url is not None)
        await self.bot.send_message(
            chat_id=payload.chat_id,
            reply_parameters=ReplyParameters(
                payload.message_id,
            ),
            text=url_list_text,
        )

        return Subscriber.Result.Ack


async def run(config: Config) -> None:
    topic = Topic.urlAliasResolution
    _LOG.debug("Subscribing to topic %s", topic)

    subscriber = await initialize_subscriber(config.event)
    converter = _UrlAliasResolver(Bot(config.telegram.token))

    await subscriber.subscribe(
        topic,
        UrlConvertMessage,
        converter.handle_payload,
    )
