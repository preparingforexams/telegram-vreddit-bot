from typing import List, Optional

from cancer.message import Message, Topic
from cancer.port.publisher import Publisher


class JointPublisher(Publisher):
    def __init__(self, publishers: List[Optional[Publisher]]):
        self.publishers = [p for p in publishers if p is not None]

    def publish(self, topic: Topic, message: Message):
        for publisher in self.publishers:
            publisher.publish(topic, message)
