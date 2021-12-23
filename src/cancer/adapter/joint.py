from dataclasses import dataclass
from typing import List

from cancer.message import Message, Topic
from cancer.port.publisher import Publisher


@dataclass
class JointPublisher(Publisher):
    publishers: List[Publisher]

    def publish(self, topic: Topic, message: Message):
        for publisher in self.publishers:
            publisher.publish(topic, message)
