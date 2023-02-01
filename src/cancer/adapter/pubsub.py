from __future__ import annotations

import logging
import os
from concurrent import futures
from dataclasses import dataclass
from typing import Callable, Type

from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient
from google.cloud.pubsub_v1.subscriber.message import Message as PubSubMessage

from cancer.message import Message, Topic
from cancer.port.publisher import Publisher, PublishingException
from cancer.port.subscriber import Subscriber, T

_LOG = logging.getLogger(__name__)


@dataclass
class PubSubConfig:
    project_id: str

    @staticmethod
    def _get_required(key: str, allow_empty: bool = False) -> str:
        result = os.getenv(key)

        if result or (allow_empty and result is not None):
            return result

        raise ValueError(f"Missing key: {key}")

    @classmethod
    def from_env(cls) -> PubSubConfig:
        return cls(
            project_id=cls._get_required("GOOGLE_CLOUD_PROJECT"),
        )


class PubSubPublisher(Publisher):
    def __init__(self, config: PubSubConfig):
        self.client = PublisherClient()
        self.prefix = f"projects/{config.project_id}/topics/"

    def publish(self, topic: Topic, message: Message):
        _LOG.debug("Publishing event %s", message.message_id)
        future = self.client.publish(
            topic=f"{self.prefix}{topic.value}",
            data=message.serialize(),
        )
        try:
            future.result(timeout=60)
        except futures.TimeoutError as e:
            raise PublishingException from e
        except Exception as e:
            raise PublishingException from e


class PubSubSubscriber(Subscriber):
    def __init__(self, config: PubSubConfig):
        self.prefix = f"projects/{config.project_id}/subscriptions/"
        self.client = SubscriberClient()

    def subscribe(
        self,
        topic: Topic,
        message_type: Type[T],
        handle: Callable[[T], Subscriber.Result],
    ):
        def _handle_message(message: PubSubMessage):
            _LOG.debug("Received a Pub/Sub message")
            try:
                decoded = message_type.deserialize(message.data)
            except Exception as e:
                _LOG.error("Could not decode message", exc_info=e)
                message.nack_with_response()
                return

            try:
                result = handle(decoded)
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
        self.client.subscribe(subscription_name, _handle_message).result()
