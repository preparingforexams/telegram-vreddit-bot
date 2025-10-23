import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Self, cast

from bs_config import Env
from bs_nats_updater import NatsConfig

from cancer.message import Topic

_LOG = logging.getLogger(__name__)


@dataclass
class DownloaderCredentials:
    username: str | None
    password: str | None
    cookie_file: Path | None

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            username=env.get_string("username"),
            password=env.get_string("password"),
            cookie_file=env.get_string("cookie-file", transform=Path),
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
        try:
            return Topic(topic_name)
        except ValueError:
            _LOG.error(
                "Could not parse topic '%s', falling back to generic",
                topic_name,
            )
            return Topic.download

    @classmethod
    def from_env(cls, env: Env) -> Self | None:
        try:
            return cls(
                credentials=DownloaderCredentials.from_env(env),
                max_file_size=int(
                    env.get_string("max-download-file-size", default="40_000_000")
                ),
                storage_dir=env.get_string(
                    "storage-dir", default=Path("downloads"), transform=Path
                ),
                topic=env.get_string(
                    "download-type",
                    default=cast(Topic, Topic.download),
                    transform=cls._parse_topic,
                ),
                upload_chat_id=int(
                    env.get_string("upload-chat-id", default="1259947317")
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
            dsn=env.get_string("sentry-dsn"),
            release=env.get_string("app-version", default="debug"),
        )


@dataclass
class TelegramConfig:
    token: str
    updater_nats: NatsConfig

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            token=env.get_string("api-key", required=True),
            updater_nats=NatsConfig.from_env(env / "nats"),
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
            endpoint=env.get_string("endpoint", required=True),
            credentials=env.get_string("credentials"),
            stream_name=env.get_string("stream-name", required=True),
        )


@dataclass
class EventConfig:
    nats: EventNatsConfig

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            nats=EventNatsConfig.from_env(env / "nats-cancer"),
        )


@dataclass
class Config:
    download: DownloaderConfig | None
    event: EventConfig
    running_signal_file: str | None
    sentry: SentryConfig
    telegram: TelegramConfig

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            download=DownloaderConfig.from_env(env),
            event=EventConfig.from_env(env),
            running_signal_file=env.get_string("running-signal-file"),
            sentry=SentryConfig.from_env(env),
            telegram=TelegramConfig.from_env(env / "telegram"),
        )
