import logging
import os
import signal
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import ParseResult, urlparse

from cancer import telegram
from cancer.adapter.publisher_pubsub import PubSubConfig, PubSubPublisher
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
    text: str,
    entity: dict,
    is_direct_chat: bool,
) -> Diagnosis | None:
    if entity["type"] == "url":
        offset = entity["offset"]
        length = entity["length"]
        url = text[offset : offset + length]
    elif entity["type"] == "text_link":
        url = entity["url"]
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


def _handle_update(publisher: Publisher, update: dict):
    message: dict | None = update.get("message")

    if not message:
        _LOG.debug("Skipping non-message update")
        return

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]

    text: str | None
    entities: list[dict] | None
    voice: dict | None

    if "text" in message:
        text = message["text"]
        entities = message.get("entities")
        voice = None
    elif "caption" in message:
        text = message["caption"]
        entities = message.get("caption_entities")
        voice = None
    elif "voice" in message:
        text = message.get("caption")
        entities = message.get("caption_entities")
        voice = message["voice"]
    else:
        _LOG.debug("Not a text or caption")
        return

    diagnosis_by_treatment: dict[Topic, list[Diagnosis]] = defaultdict(list)
    is_direct_chat = chat_id == user_id
    if text and entities:
        for entity in entities:
            diagnosis = _diagnose_cancer(text, entity, is_direct_chat=is_direct_chat)
            if diagnosis:
                diagnosis_by_treatment[diagnosis.treatment].append(diagnosis)

    if is_direct_chat and voice:
        diagnosis_by_treatment[Topic.voiceDownload].append(
            Diagnosis(
                cancer=None,  # type: ignore
                case=f"{voice['file_id']}::{voice['file_size']}",
                is_private=True,
            )
        )

    if not diagnosis_by_treatment:
        _LOG.debug("Message was healthy")
        return

    try:
        telegram.set_message_reaction(
            chat_id=chat_id,
            message_id=message["message_id"],
            emoji="🫡" if is_direct_chat else "😡",
        )
    except Exception as e:
        # Don't really care if this fails.
        _LOG.error("Could not set message reaction", exc_info=e)

    for treatment in Topic:
        diagnoses = diagnosis_by_treatment[treatment]
        if not diagnoses:
            _LOG.debug("No diagnosed cases for treatment %s", treatment)
            continue

        event = _make_message(chat_id, message["message_id"], treatment, diagnoses)

        try:
            publisher.publish(treatment, event)
            _LOG.info("Published event on topic %s", treatment.value)
        except PublishingException as e:
            _LOG.error("Could not publish event", exc_info=e)
            raise


def _init_publisher() -> Publisher:
    if os.getenv("PUBLISHER_STUB") == "true":
        from cancer.adapter.publisher_stub import StubPublisher

        return StubPublisher()

    try:
        return PubSubPublisher(PubSubConfig.from_env())
    except ValueError as e:
        _LOG.warning("Could not initialize Publisher", exc_info=e)
        raise


def run() -> None:
    telegram.check()

    publisher: Publisher = _init_publisher()

    received_sigterm = False

    def should_run() -> bool:
        return not received_sigterm

    def on_sigterm(*args):
        nonlocal received_sigterm
        received_sigterm = True

    signal.signal(signal.SIGTERM, on_sigterm)

    telegram.handle_updates(should_run, lambda u: _handle_update(publisher, u))
