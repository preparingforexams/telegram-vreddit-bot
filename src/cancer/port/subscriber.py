import abc
from enum import Enum, auto
from typing import Callable, TypeVar, Type

from cancer.message import Message, Topic

T = TypeVar("T", bound=Message)


class Subscriber(abc.ABC):
    class Result(Enum):
        Ack = auto()
        Drop = auto()
        Requeue = auto()

    @abc.abstractmethod
    def subscribe(
        self, topic: Topic, message_type: Type[T], handle: Callable[[T], Result]
    ):
        pass
