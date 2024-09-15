import abc
from collections.abc import Callable
from enum import Enum, auto
from typing import TypeVar

from cancer.message import Message, Topic

T = TypeVar("T", bound=Message)


class Subscriber(abc.ABC):
    class Result(Enum):
        Ack = auto()
        Drop = auto()
        Requeue = auto()

    @abc.abstractmethod
    def subscribe(
        self, topic: Topic, message_type: type[T], handle: Callable[[T], Result]
    ):
        pass
