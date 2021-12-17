from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from . import Message


@dataclass
class DownloadMessage(Message):
    chat_id: int
    message_id: int
    urls: List[str]

    def instagram(self) -> DownloadMessage:
        self.topic = lambda: os.getenv("MQTT_TOPIC_INSTA_DOWNLOAD")  # noqa
        return self

    @classmethod
    def topic(cls) -> str:
        return os.getenv("MQTT_TOPIC_DOWNLOAD")
