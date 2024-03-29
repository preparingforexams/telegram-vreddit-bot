from dataclasses import dataclass

from .message import Message


@dataclass
class YoutubeUrlConvertMessage(Message):
    urls: list[str]
