import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from bs_config import Env
from bs_nats_updater import NatsConfig

from cancer.message import Topic

_LOG = logging.getLogger(__name__)


@dataclass
class DownloaderCredentials:
    username: str | None
    password: str | None
    cookie_file: str | None

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            username=env.get_string("USERNAME"),
            password=env.get_string("PASSWORD"),
            cookie_file=env.get_string("COOKIE_FILE"),
        )


@dataclass
class DownloaderConfig:
    credentials: DownloaderCredentials
    max_file_size: int
    storage_dir: Path
    topic: Topic
    upload_chat_id: int

    @staticmethod
    def _parse_topic(topic_name: str) -> Topic:
        match topic_name:
            case "insta":
                return Topic.instaDownload
            case "youtube":
                return Topic.youtubeDownload
            case "tiktok":
                return Topic.tiktokDownload
            case "twitter":
                return Topic.twitterDownload
            case "vimeo":
                return Topic.vimeoDownload
            case download_type:
                _LOG.info(
                    "Using generic download topic for download type %s", download_type
                )
                return Topic.download

    @classmethod
    def from_env(cls, env: Env) -> Self | None:
        try:
            return cls(
                credentials=DownloaderCredentials.from_env(env),
                max_file_size=int(
                    env.get_string("MAX_DOWNLOAD_FILE_SIZE", default="40_000_000")
                ),
                storage_dir=Path(env.get_string("STORAGE_DIR", default="downloads")),
                topic=cls._parse_topic(
                    env.get_string("DOWNLOAD_TYPE", default="generic")
                ),
                upload_chat_id=int(
                    env.get_string("UPLOAD_CHAT_ID", default="1259947317")
                ),
            )
        except ValueError as e:
            _LOG.info("Downloader config is missing %s", e)
            return None


@dataclass
class SentryConfig:
    dsn: str | None
    release: str

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            dsn=env.get_string("SENTRY_DSN"),
            release=env.get_string("APP_VERSION", default="debug"),
        )


@dataclass
class TelegramConfig:
    token: str
    updater_nats: NatsConfig

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            token=env.get_string("API_KEY", required=True),
            updater_nats=NatsConfig.from_env(env.scoped("NATS_")),
        )


@dataclass
class EventNatsConfig:
    endpoint: str
    credentials: str | None
    stream_name: str

    def get_publish_subject(self, topic: Topic) -> str:
        return f"{self.stream_name}.{topic.value}"

    def get_consumer_name(self, topic: Topic) -> str:
        return topic.value

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            endpoint=env.get_string("ENDPOINT", required=True),
            credentials=env.get_string("CREDENTIALS"),
            stream_name=env.get_string("STREAM_NAME", required=True),
        )


@dataclass
class EventConfig:
    nats: EventNatsConfig

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            nats=EventNatsConfig.from_env(env.scoped("NATS_CANCER_")),
        )


@dataclass
class Config:
    download: DownloaderConfig | None
    event: EventConfig
    sentry: SentryConfig
    telegram: TelegramConfig

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            download=DownloaderConfig.from_env(env),
            event=EventConfig.from_env(env),
            sentry=SentryConfig.from_env(env),
            telegram=TelegramConfig.from_env(env.scoped("TELEGRAM_")),
        )
