from __future__ import annotations

from dataclasses import dataclass
from typing import List

from . import Message


@dataclass
class DownloadMessage(Message):
    chat_id: int
    message_id: int
    urls: List[str]
