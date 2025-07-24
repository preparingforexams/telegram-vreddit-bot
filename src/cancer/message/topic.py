from enum import Enum

from .download import DownloadMessage
from .voice import VoiceMessage
from .youtube_url_convert import YoutubeUrlConvertMessage


class Topic(str, Enum):
    download = "download"
    instaDownload = "insta-download"
    youtubeDownload = "youtube-download"
    youtubeUrlConvert = "youtube-url-convert"
    tiktokDownload = "tiktok-download"
    twitterDownload = "twitter-download"
    urlAliasResolution = "url-alias-resolution"
    vimeoDownload = "vimeo-download"
    voiceDownload = "voice-download"

    def create_message(self, chat_id: int, message_id: int, urls: list[str]):
        match self:
            case Topic.youtubeUrlConvert:
                return YoutubeUrlConvertMessage(chat_id, message_id, urls)
            case Topic.voiceDownload:
                file_id, file_size = urls[0].rsplit("::", maxsplit=1)
                return VoiceMessage(
                    chat_id=chat_id,
                    message_id=message_id,
                    file_id=file_id,
                    file_size=int(file_size),
                )
            case (
                Topic.download
                | Topic.instaDownload
                | Topic.youtubeDownload
                | Topic.tiktokDownload
                | Topic.twitterDownload
                | Topic.vimeoDownload
            ):
                return DownloadMessage(chat_id, message_id, urls)
            case _:
                raise ValueError(f"Unknown message for type {self}")
