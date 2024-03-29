from dataclasses import dataclass

from .message import Message


@dataclass
class DownloadMessage(Message):
    urls: list[str]
