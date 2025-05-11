import logging
import signal
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast
from urllib.parse import ParseResult, urlparse

from telegram import MessageEntity, Update, Voice
from telegram.constants import ChatType, MessageEntityType
from telegram.ext import ApplicationBuilder, MessageHandler

from cancer.config import Config, EventConfig
from cancer.message import Message, Topic
from cancer.port.publisher import Publisher, PublishingException

_LOG = logging.getLogger(__name__)


@dataclass
class Cancer:
    host: str
    treatment: Topic | None
    private_treatment: Topic | None = None
    path: str | None = None

    def matches(self, symptoms: ParseResult) -> bool:
        if symptoms.netloc.startswith(self.host):
            return not self.path or symptoms.path.startswith(self.path)
        return False

    def get_treatment(self, *, is_private: bool) -> Topic | None:
        if is_private:
            return self.private_treatment or self.treatment

        return self.treatment


_CANCERS = [
    Cancer(host="twitter.com", treatment=Topic.twitterDownload),
    Cancer(host="mobile.twitter.com", treatment=Topic.twitterDownload),
    Cancer("v.redd.it", Topic.download),
    Cancer("www.reddit.com", Topic.download),
    Cancer("cdn.discordapp.com", Topic.download),
    Cancer("instagram.com", Topic.instaDownload),
    Cancer("www.instagram.com", Topic.instaDownload),
    Cancer("facebook.com", Topic.instaDownload),
    Cancer("www.facebook.com", Topic.instaDownload),
    # Cancer("vm.tiktok.com", Topic.tiktokDownload),
    # Cancer("www.tiktok.com", Topic.tiktokDownload),
    Cancer(
        host="youtube.com",
        path="/shorts/",
        treatment=Topic.youtubeUrlConvert,
        private_treatment=Topic.youtubeDownload,
    ),
    Cancer(
        host="www.youtube.com",
        path="/shorts/",
        treatment=Topic.youtubeUrlConvert,
        private_treatment=Topic.youtubeDownload,
    ),
    Cancer(
        host="youtu.be",
        private_treatment=Topic.youtubeDownload,
        treatment=None,
    ),
    Cancer(
        host="www.youtube.com",
        path="/watch",
        private_treatment=Topic.youtubeDownload,
        treatment=None,
    ),
    Cancer(
        host="youtube.com",
        path="/watch",
        private_treatment=Topic.youtubeDownload,
        treatment=None,
    ),
    Cancer(
        host="gfycat.com",
        treatment=Topic.download,
    ),
    Cancer(
        host="www.linkedin.com",
        treatment=Topic.download,
        path="/posts",
    ),
    Cancer(
        host="linkedin.com",
        treatment=Topic.download,
        path="/posts",
    ),
    Cancer(
        host="vimeo.com",
        treatment=None,
        private_treatment=Topic.vimeoDownload,
    ),
]


@dataclass
class Diagnosis:
    cancer: Cancer
    is_private: bool
    case: str

    @property
    def has_treatment(self) -> bool:
        return self.cancer.get_treatment(is_private=self.is_private) is not None

    @property
    def treatment(self) -> Topic:
        treatment = self.cancer.get_treatment(is_private=self.is_private)
        if treatment is None:
            raise ValueError
        return treatment


@dataclass
class Cure:
    cure_path: str
    cancer: str


@dataclass
class Drug:
    drug_id: str
    cancer: str


def _diagnose_cancer(
    parse_entity: Callable[[MessageEntity], str],
    entity: MessageEntity,
    is_direct_chat: bool,
) -> Diagnosis | None:
    if entity.type == MessageEntityType.URL:
        url = parse_entity(entity)
    elif entity.type == MessageEntityType.TEXT_LINK:
        url = cast(str, entity.url)
    else:
        return None

    _LOG.info("Extracted URL %s", url)
    symptoms = urlparse(url)
    for cancer in _CANCERS:
        if cancer.matches(symptoms):
            diagnosis = Diagnosis(
                cancer=cancer,
                case=url,
                is_private=is_direct_chat,
            )
            if not diagnosis.has_treatment:
                continue

            return diagnosis

    return None


def _make_message(
    chat_id: int,
    message_id: int,
    treatment: Topic,
    diagnoses: list[Diagnosis],
) -> Message:
    return treatment.create_message(chat_id, message_id, [d.case for d in diagnoses])


class _CancerBot:
    def __init__(self, publisher: Publisher) -> None:
        self.publisher = publisher

    async def handle_update(self, update: Update, _):
        message = update.message

        if not message:
            _LOG.debug("Skipping non-message update")
            return

        chat_id = message.chat.id
        is_direct_chat = message.chat.type == ChatType.PRIVATE

        parse_entity: Callable[[MessageEntity], str]
        entities: tuple[MessageEntity, ...]
        voice: Voice | None

        if message.text:
            entities = message.entities
            parse_entity = message.parse_entity
            voice = None
        elif voice := message.voice:
            entities = message.caption_entities
            parse_entity = message.parse_caption_entity
            voice = voice
        elif message.caption:
            entities = message.caption_entities
            parse_entity = message.parse_caption_entity
            voice = None
        else:
            _LOG.debug("Not a text or caption")
            return

        diagnosis_by_treatment: dict[Topic, list[Diagnosis]] = defaultdict(list)
        if entities:
            for entity in entities:
                diagnosis = _diagnose_cancer(
                    parse_entity, entity, is_direct_chat=is_direct_chat
                )
                if diagnosis:
                    diagnosis_by_treatment[diagnosis.treatment].append(diagnosis)

        if is_direct_chat and voice:
            diagnosis_by_treatment[Topic.voiceDownload].append(
                Diagnosis(
                    cancer=None,  # type: ignore
                    case=f"{voice.file_id}::{voice.file_size}",
                    is_private=True,
                )
            )

        if not diagnosis_by_treatment:
            _LOG.debug("Message was healthy")
            return

        try:
            await message.set_reaction(
                reaction="🫡" if is_direct_chat else "😡",
            )
        except Exception as e:
            # Don't really care if this fails.
            _LOG.error("Could not set message reaction", exc_info=e)

        for treatment in Topic:
            diagnoses = diagnosis_by_treatment[treatment]
            if not diagnoses:
                _LOG.debug("No diagnosed cases for treatment %s", treatment)
                continue

            event = _make_message(chat_id, message.message_id, treatment, diagnoses)

            try:
                await self.publisher.publish(treatment, event)
                _LOG.info("Published event on topic %s", treatment.value)
            except PublishingException as e:
                _LOG.error("Could not publish event", exc_info=e)
                raise


def _init_publisher(config: EventConfig) -> Publisher:
    broker = config.broker

    if broker == "nats":
        nats_config = config.nats
        if nats_config is None:
            raise ValueError("nats config is required when broker is nats")

        from cancer.adapter.publisher_nats import NatsPublisher

        return NatsPublisher(nats_config)

    if broker == "pubsub":
        pubsub_config = config.pub_sub
        if pubsub_config is None:
            raise ValueError("pubsub config is required when broker is pubsub")

        from cancer.adapter.publisher_pubsub import PubSubPublisher

        return PubSubPublisher(pubsub_config)

    raise ValueError("Invalid event config")


def run(config: Config) -> None:
    publisher: Publisher = _init_publisher(config.event)
    cancer_bot = _CancerBot(publisher)

    app = (
        ApplicationBuilder()
        .token(config.telegram.token)
        .post_stop(lambda _: publisher.close())
        .build()
    )

    app.add_handler(MessageHandler(filters=None, callback=cancer_bot.handle_update))

    app.run_polling(
        stop_signals=[signal.SIGTERM, signal.SIGINT],
    )
