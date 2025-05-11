import asyncio
import logging
import signal
import sys

from cancer.config import EventConfig
from cancer.port.subscriber import Subscriber

_LOG = logging.getLogger(__name__)


def _close_subscriber(subscriber: Subscriber) -> None:
    asyncio.ensure_future(subscriber.close())


def _close_subscriber_on_signal(subscriber: Subscriber):
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, _close_subscriber, subscriber)
    loop.add_signal_handler(signal.SIGTERM, _close_subscriber, subscriber)


async def initialize_subscriber(config: EventConfig) -> Subscriber:
    subscriber: Subscriber

    broker = config.broker
    nats_config = config.nats
    pubsub_config = config.pub_sub

    if broker == "nats" and nats_config is not None:
        _LOG.info("Using NATS subscriber")
        from cancer.adapter.publisher_nats import NatsSubscriber

        subscriber = NatsSubscriber(nats_config)
    elif broker == "pubsub" and pubsub_config is not None:
        _LOG.info("Using PubSub subscriber")
        from cancer.adapter.publisher_pubsub import PubSubSubscriber

        subscriber = PubSubSubscriber(pubsub_config)
    else:
        _LOG.error("Invalid event config")
        sys.exit(1)

    _close_subscriber_on_signal(subscriber)

    return subscriber
