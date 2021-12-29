from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .message import Message


@dataclass
class DownloadMessage(Message):
    chat_id: int
    message_id: int
    urls: List[str]
