import logging

from cancer.message import Message, Topic
from cancer.port.publisher import Publisher

_LOG = logging.getLogger(__name__)


class StubPublisher(Publisher):
    def publish(self, topic: Topic, message: Message):
        _LOG.info(
            "Dropping message for topic %s in stub publisher: %s",
            topic,
            message,
        )
