from dataclasses import dataclass

from .message import Message


@dataclass
class VoiceMessage(Message):
    file_id: str
    file_size: int
