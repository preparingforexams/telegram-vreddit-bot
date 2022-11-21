import logging
import signal
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, List, Dict
from urllib.parse import urlparse, ParseResult

from cancer import telegram
from cancer.adapter.pubsub import PubSubConfig, PubSubPublisher
from cancer.message import (
    Message,
    Topic,
)
from cancer.port.publisher import Publisher, PublishingException

_LOG = logging.getLogger(__name__)


@dataclass
class Cancer:
    host: str
    treatment: Topic
    path: Optional[str] = None

    def matches(self, symptoms: ParseResult) -> bool:
        if symptoms.netloc.startswith(self.host):
            return not self.path or symptoms.path.startswith(self.path)
        return False


_CANCERS = [
    Cancer(host="twitter.com", treatment=Topic.twitterDownload),
    Cancer("v.redd.it", Topic.download),
    Cancer("www.reddit.com", Topic.download),
    Cancer("cdn.discordapp.com", Topic.download),
    Cancer("instagram.com", Topic.instaDownload),
    Cancer("www.instagram.com", Topic.instaDownload),
    Cancer("facebook.com", Topic.instaDownload),
    Cancer("www.facebook.com", Topic.instaDownload),
    Cancer("vm.tiktok.com", Topic.tiktokDownload),
    Cancer("www.tiktok.com", Topic.tiktokDownload),
    Cancer(
        host="youtube.com",
        path="/shorts/",
        treatment=Topic.youtubeUrlConvert,
    ),
    Cancer(
        host="www.youtube.com",
        path="/shorts/",
        treatment=Topic.youtubeUrlConvert,
    ),
    Cancer(
        host="youtu.be",
        treatment=Topic.youtubeDownload,
    ),
    Cancer(
        host="www.youtube.com",
        path="/watch",
        treatment=Topic.youtubeDownload,
    ),
    Cancer(
        host="youtube.com",
        path="/watch",
        treatment=Topic.youtubeDownload,
    ),
]


@dataclass
class Diagnosis:
    cancer: Cancer
    case: str


@dataclass
class Cure:
    cure_path: str
    cancer: str


@dataclass
class Drug:
    drug_id: str
    cancer: str


def _diagnose_cancer(text: str, entity: dict) -> Optional[Diagnosis]:
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
            return Diagnosis(cancer, url)

    return None


def _make_message(
    chat_id: int,
    message_id: int,
    treatment: Topic,
    diagnoses: List[Diagnosis],
) -> Message:
    return treatment.create_message(chat_id, message_id, [d.case for d in diagnoses])


def _handle_update(publisher: Publisher, update: dict):
    message: Optional[dict] = update.get("message")

    if not message:
        _LOG.debug("Skipping non-message update")
        return

    text: str
    entities: Optional[List[dict]]

    if "text" in message:
        text = message["text"]
        entities = message.get("entities")
    elif "caption" in message:
        text = message["caption"]
        entities = message.get("caption_entities")
    else:
        _LOG.debug("Not a text or caption")
        return

    if not entities:
        _LOG.debug("No entities found in message")
        return

    diagnosis_by_treatment: Dict[Topic, List[Diagnosis]] = defaultdict(list)
    for entity in entities:
        diagnosis = _diagnose_cancer(text, entity)
        if diagnosis:
            diagnosis_by_treatment[diagnosis.cancer.treatment].append(diagnosis)

    if not diagnosis_by_treatment:
        _LOG.debug("Message was healthy")
        return

    for treatment in Topic:
        diagnoses = diagnosis_by_treatment[treatment]
        if not diagnoses:
            _LOG.debug("No diagnosed cases for treatment %s", treatment)
            continue

        event = _make_message(
            message["chat"]["id"], message["message_id"], treatment, diagnoses
        )

        try:
            publisher.publish(treatment, event)
            _LOG.info("Published event on topic %s", treatment.value)
        except PublishingException as e:
            _LOG.error("Could not publish event", exc_info=e)
            raise


def _init_publisher() -> Optional[Publisher]:
    try:
        return PubSubPublisher(PubSubConfig.from_env())
    except ValueError as e:
        _LOG.warning("Could not initialize Publisher", exc_info=e)
        return None


def run():
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
