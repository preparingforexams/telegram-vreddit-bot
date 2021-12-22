import abc
from typing import List

from cancer.message import Message


class Publisher(abc.ABC):

    @abc.abstractmethod
    def publish(self, topic: str, messages: Message):
        pass
