import asyncio
import logging
import signal

from cancer.adapter.publisher_nats import NatsSubscriber
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

    nats_config = config.nats
    _LOG.info("Using NATS subscriber")
    subscriber = NatsSubscriber(nats_config)

    _close_subscriber_on_signal(subscriber)

    return subscriber
