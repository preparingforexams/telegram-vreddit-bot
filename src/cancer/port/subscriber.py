import abc
from collections.abc import Awaitable, Callable
from enum import Enum, auto

from cancer.message import Message, Topic

type MessageCallback[T] = Callable[[T], Awaitable[Subscriber.Result]]


class Subscriber(abc.ABC):
    class Result(Enum):
        Ack = auto()
        Drop = auto()
        Requeue = auto()

    @abc.abstractmethod
    async def subscribe[T: Message](
        self, topic: Topic, message_type: type[T], handle: MessageCallback[T]
    ) -> None:
        pass
