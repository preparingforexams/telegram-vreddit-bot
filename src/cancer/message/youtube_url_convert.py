from dataclasses import dataclass

from .message import Message


@dataclass
class UrlConvertMessage(Message):
    urls: list[str]
