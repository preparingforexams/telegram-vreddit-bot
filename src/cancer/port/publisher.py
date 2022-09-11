import abc

from cancer.message import Message, Topic


class PublishingException(Exception):
    pass


class Publisher(abc.ABC):
    @abc.abstractmethod
    def publish(self, topic: Topic, message: Message):
        pass
