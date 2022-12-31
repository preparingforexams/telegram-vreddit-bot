from enum import Enum
from typing import List

from .download import DownloadMessage
from .voice import VoiceMessage
from .youtube_url_convert import YoutubeUrlConvertMessage


class Topic(str, Enum):
    download = "download"
    instaDownload = "instaDownload"
    youtubeDownload = "youtubeDownload"
    youtubeUrlConvert = "youtubeUrlConvert"
    tiktokDownload = "tiktokDownload"
    twitterDownload = "twitterDownload"
    voiceDownload = "voiceDownload"

    def create_message(self, chat_id: int, message_id: int, urls: List[str]):
        if self == Topic.youtubeUrlConvert:
            return YoutubeUrlConvertMessage(chat_id, message_id, urls)
        elif self == Topic.voiceDownload:
            file_id, file_size = urls[0].rsplit("::", maxsplit=1)
            return VoiceMessage(
                chat_id=chat_id,
                message_id=message_id,
                file_id=file_id,
                file_size=int(file_size),
            )
        elif self in {
            Topic.download,
            Topic.instaDownload,
            Topic.youtubeDownload,
            Topic.tiktokDownload,
            Topic.twitterDownload,
        }:
            return DownloadMessage(chat_id, message_id, urls)
        else:
            raise ValueError(f"Unknown message for type {self}")
