from dataclasses import dataclass
from typing import List

from .message import Message


@dataclass
class YoutubeUrlConvertMessage(Message):
    chat_id: int
    message_id: int
    urls: List[str]
