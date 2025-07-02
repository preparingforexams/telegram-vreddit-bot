import asyncio
import logging

from nats.aio.client import Client, RawCredentials
from nats.errors import TimeoutError
from nats.js.client import JetStreamContext
from nats.js.errors import ServiceUnavailableError

from cancer.config import EventNatsConfig
from cancer.message import Message, Topic
from cancer.port.publisher import Publisher, PublishingException
from cancer.port.subscriber import MessageCallback, Subscriber

_LOG = logging.getLogger(__name__)


class NatsPublisher(Publisher):
    def __init__(self, config: EventNatsConfig):
        self.config = config
        self._client: Client | None = None

    async def _get_client(self) -> Client:
        client = self._client
        if client is None:
            client = Client()
            credentials = self.config.credentials
            raw_credentials = RawCredentials(credentials) if credentials else None
            await client.connect(
                self.config.endpoint,
                allow_reconnect=True,
                user_credentials=raw_credentials,
            )
            self._client = client
        return client

    async def publish(self, topic: Topic, message: Message):
        _LOG.debug("Publishing event %s", message.message_id)
        client = await self._get_client()
        jetstream = client.jetstream()

        try:
            await jetstream.publish(
                subject=self.config.get_publish_subject(topic),
                payload=message.serialize(),
                stream=self.config.stream_name,
            )
        except Exception as e:
            raise PublishingException from e

    async def close(self) -> None:
        if (client := self._client) is not None:
            _LOG.info("Draining NATS client")
            await client.drain()
            _LOG.info("Closing NATS client")
            await client.close()
        _LOG.info("NATS publisher closed")


class NatsSubscriber(Subscriber):
    def __init__(self, config: EventNatsConfig):
        self.config = config
        self._client: Client | None = None

    async def _get_client(self) -> Client:
        client = self._client
        if client is None:
            client = Client()
            await client.connect(
                self.config.endpoint,
                allow_reconnect=True,
                user_credentials=RawCredentials(self.config.credentials),
            )
            self._client = client
        return client

    async def subscribe[T: Message](
        self,
        topic: Topic,
        message_type: type[T],
        handle: MessageCallback,
    ):
        client = await self._get_client()
        jetstream = client.jetstream()
        sub: JetStreamContext.PullSubscription = await jetstream.pull_subscribe_bind(
            consumer=self.config.get_consumer_name(topic),
            stream=self.config.stream_name,
        )

        while not (client.is_draining or client.is_closed):
            try:
                msgs = await sub.fetch(timeout=60)
            except TimeoutError:
                _LOG.debug("Subscription fetch timed out")
                continue
            except ServiceUnavailableError as e:
                _LOG.error(
                    "NATS service unavailable. Retrying after a short wait...",
                    exc_info=e,
                )
                await asyncio.sleep(10)
                continue
            except Exception as e:
                _LOG.error("Could not fetch messages", exc_info=e)
                continue

            for message in msgs:
                try:
                    decoded = message_type.deserialize(message.data)
                except Exception as e:
                    _LOG.error("Could not decode message", exc_info=e)
                    await message.term()
                    continue

                try:
                    result = await handle(decoded)
                except Exception as e:
                    _LOG.error(
                        "Handler failed to handle message, requeuing", exc_info=e
                    )
                    await message.nak()
                else:
                    match result:
                        case Subscriber.Result.Ack:
                            await message.ack()
                        case Subscriber.Result.Drop:
                            _LOG.warning("Dropping message")
                            await message.term()
                        case Subscriber.Result.Requeue:
                            _LOG.info("Requeuing message due to handler result")
                            await message.nak()
                        case _:
                            raise ValueError(f"Unknown event handler result: {result}")

    async def close(self) -> None:
        if (client := self._client) is not None:
            _LOG.info("Draining NATS client")
            await client.drain()
            _LOG.info("Closing NATS client")
            await client.close()
        _LOG.info("NATS subscriber closed")
