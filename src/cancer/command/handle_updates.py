import logging
import signal
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Dict
from urllib.parse import urlparse, ParseResult

from cancer import telegram
from cancer.adapter.joint import JointPublisher
from cancer.adapter.mqtt import MqttPublisher, MqttConfig
from cancer.adapter.rabbit import RabbitPublisher, RabbitConfig
from cancer.message import (
    DownloadMessage,
    Message,
    Topic,
    YoutubeUrlConvertMessage,
)
from cancer.port.publisher import Publisher

_LOG = logging.getLogger(__name__)


class Treatment(Enum):
    DOWNLOAD = auto()
    INSTA_DOWNLOAD = auto()
    YOUTUBE_URL_CONVERT = auto()

    def topic(self) -> Topic:
        if self == Treatment.DOWNLOAD:
            return Topic.download

        if self == Treatment.INSTA_DOWNLOAD:
            return Topic.instaDownload

        if self == Treatment.YOUTUBE_URL_CONVERT:
            return Topic.youtubeUrlConvert

        raise ValueError(f"No topic for Treatment {self}")


@dataclass
class Cancer:
    host: str
    treatment: Treatment
    path: Optional[str] = None

    def matches(self, symptoms: ParseResult) -> bool:
        if symptoms.netloc.startswith(self.host):
            return not self.path or symptoms.path.startswith(self.path)
        return False


_CANCERS = [
    Cancer(host="twitter.com", treatment=Treatment.DOWNLOAD),
    Cancer("v.redd.it", Treatment.DOWNLOAD),
    Cancer("www.reddit.com", Treatment.DOWNLOAD),
    Cancer("instagram.com", Treatment.INSTA_DOWNLOAD),
    Cancer("www.instagram.com", Treatment.INSTA_DOWNLOAD),
    Cancer("facebook.com", Treatment.INSTA_DOWNLOAD),
    Cancer("www.facebook.com", Treatment.INSTA_DOWNLOAD),
    Cancer("vm.tiktok.com", Treatment.DOWNLOAD),
    Cancer(
        host="youtube.com",
        path="/shorts/",
        treatment=Treatment.YOUTUBE_URL_CONVERT,
    ),
    Cancer(
        host="youtu.be",
        treatment=Treatment.DOWNLOAD,
    ),
    Cancer(
        host="youtube.com",
        path="/watch",
        treatment=Treatment.DOWNLOAD,
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
        url = text[offset:offset + length]
    elif entity["type"] == "text_link":
        url = entity["url"]
    else:
        return None

    _LOG.info("Extracted URL %s", url)
    symptoms = urlparse(url)
    for cancer in _CANCERS:
        if cancer.matches(symptoms):
            return Diagnosis(cancer, url)


def _make_message(
        chat_id: int,
        message_id: int,
        treatment: Treatment,
        diagnoses: List[Diagnosis],
) -> Message:
    if treatment == Treatment.DOWNLOAD:
        message = DownloadMessage(chat_id, message_id, [d.case for d in diagnoses])
        return message

    if treatment == Treatment.INSTA_DOWNLOAD:
        message = DownloadMessage(chat_id, message_id, [d.case for d in diagnoses])
        return message

    if treatment == Treatment.YOUTUBE_URL_CONVERT:
        message = YoutubeUrlConvertMessage(chat_id, message_id, [d.case for d in diagnoses])
        return message

    raise ValueError(f"Unknown treatment: {treatment}")


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

    diagnosis_by_treatment: Dict[Treatment, List[Diagnosis]] = defaultdict(list)
    for entity in entities:
        diagnosis = _diagnose_cancer(text, entity)
        if diagnosis:
            diagnosis_by_treatment[diagnosis.cancer.treatment].append(diagnosis)

    if not diagnosis_by_treatment:
        _LOG.debug("Message was healthy")
        return

    # TODO: cut out the middle man ("Treatment")
    for treatment in Treatment:
        diagnoses = diagnosis_by_treatment[treatment]
        if not diagnoses:
            _LOG.debug("No diagnosed cases for treatment %s", treatment)
            continue

        topic = treatment.topic()
        event = _make_message(message["chat"]["id"], message["message_id"], treatment, diagnoses)

        try:
            publisher.publish(topic, event)
            _LOG.info("Published event on topic %s", topic.value)
        except Exception as e:
            _LOG.error("Could not publish event", exc_info=e)
            raise


def _init_mqtt_publisher() -> Optional[Publisher]:
    try:
        return MqttPublisher(MqttConfig.from_env())
    except ValueError as e:
        _LOG.warning("Could not initialize MQTT", exc_info=e)
        return None


def _init_rabbit_publisher() -> Optional[Publisher]:
    try:
        return RabbitPublisher(RabbitConfig.from_env())
    except ValueError as e:
        _LOG.warning("Could not initialize RabbitMQ", exc_info=e)
        return None


def run():
    telegram.check()

    publisher: Publisher = JointPublisher([
        _init_mqtt_publisher(),
        _init_rabbit_publisher(),
    ])

    received_sigterm = False

    def should_run() -> bool:
        return not received_sigterm

    def on_sigterm(*args):
        nonlocal received_sigterm
        received_sigterm = True

    signal.signal(signal.SIGTERM, on_sigterm)

    telegram.handle_updates(should_run, lambda u: _handle_update(publisher, u))
