from enum import Enum
from typing import Type, List

from .download import DownloadMessage
from .message import Message
from .youtube_url_convert import YoutubeUrlConvertMessage


class Topic(Enum):
    download = "download"
    instaDownload = "instaDownload"
    youtubeDownload = "youtubeDownload"
    youtubeUrlConvert = "youtubeUrlConvert"

    def create_message(self, chat_id: int, message_id: int, urls: List[str]):
        clazz: Type[Message]
        if self == Topic.youtubeUrlConvert:
            clazz = YoutubeUrlConvertMessage
        elif self in {Topic.download, Topic.instaDownload, Topic.youtubeDownload}:
            clazz = DownloadMessage
        else:
            raise ValueError(f"Unknown message for type {self}")

        return clazz(chat_id, message_id, urls)
