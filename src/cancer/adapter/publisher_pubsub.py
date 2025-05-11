import asyncio
import functools
import logging
from concurrent import futures

from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient
from google.cloud.pubsub_v1.subscriber.message import Message as PubSubMessage

from cancer.config import EventPubSubConfig
from cancer.message import Message, Topic
from cancer.port.publisher import Publisher, PublishingException
from cancer.port.subscriber import MessageCallback, Subscriber

_LOG = logging.getLogger(__name__)


class PubSubPublisher(Publisher):
    def __init__(self, config: EventPubSubConfig):
        self.client = PublisherClient()
        self.prefix = f"projects/{config.project_id}/topics/"

    async def publish(self, topic: Topic, message: Message):
        _LOG.debug("Publishing event %s", message.message_id)
        future = self.client.publish(
            topic=f"{self.prefix}{topic.value}",
            data=message.serialize(),
        )

        loop = asyncio.get_running_loop()

        try:
            await loop.run_in_executor(
                None,
                functools.partial(future.result, timeout=60),
            )
        except futures.TimeoutError as e:
            raise PublishingException from e
        except Exception as e:
            raise PublishingException from e

    async def close(self) -> None:
        self.client.stop()


class PubSubSubscriber(Subscriber):
    def __init__(self, config: EventPubSubConfig):
        self.prefix = f"projects/{config.project_id}/subscriptions/"
        self.client = SubscriberClient()

    async def subscribe[T: Message](
        self,
        topic: Topic,
        message_type: type[T],
        handle: MessageCallback[T],
    ) -> None:
        loop = asyncio.get_running_loop()

        def _handle_message(message: PubSubMessage):
            _LOG.debug("Received a Pub/Sub message")
            try:
                decoded = message_type.deserialize(message.data)
            except Exception as e:
                _LOG.error("Could not decode message", exc_info=e)
                message.nack_with_response()
                return

            try:
                future = asyncio.run_coroutine_threadsafe(handle(decoded), loop)
                _LOG.info("Waiting for handler future to complete")
                result = future.result()
                _LOG.info("Handler future completed")
            except Exception as e:
                _LOG.error("Handler failed to handle message, requeuing", exc_info=e)
                message.nack_with_response()
            else:
                if result == Subscriber.Result.Ack:
                    message.ack_with_response().result()
                elif result == Subscriber.Result.Drop:
                    _LOG.warning("Dropping message by acknowledging")
                    message.ack_with_response().result()
                elif result == Subscriber.Result.Requeue:
                    message.nack_with_response().result()
                else:
                    raise ValueError(f"Unknown event handler result: {result}")

        subscription_name = f"{self.prefix}{topic.value}"
        subscribe_future = self.client.subscribe(subscription_name, _handle_message)
        await loop.run_in_executor(None, subscribe_future.result)
        _LOG.info("Subscription ended")

    async def close(self) -> None:
        _LOG.info("Closing Pub/Sub subscriber")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.client.close)
        _LOG.info("Pub/Sub subscriber closed")
