import logging
import os
import signal
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Dict
from urllib.parse import urlparse, ParseResult

from cancer import telegram, mqtt
from cancer.message import Message
from cancer.message.download import DownloadMessage
from cancer.message.youtube_url_convert import YoutubeUrlConvertMessage

_API_KEY = os.getenv("TELEGRAM_API_KEY")
_STORAGE_DIR = os.getenv("STORAGE_DIR", "downloads")
_UPLOAD_CHAT = os.getenv("UPLOAD_CHAT_ID", "1259947317")

_LOG = logging.getLogger(__name__)


class Treatment(Enum):
    DOWNLOAD = auto()
    YOUTUBE_URL_CONVERT = auto()


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
    # Cancer("instagram.com", Treatment.DOWNLOAD),
    # Cancer("www.instagram.com", Treatment.DOWNLOAD),
    Cancer("facebook.com", Treatment.DOWNLOAD),
    Cancer("www.facebook.com", Treatment.DOWNLOAD),
    # Cancer("vm.tiktok.com", Treatment.DOWNLOAD),
    Cancer(
        host="youtube.com",
        path="/shorts/",
        treatment=Treatment.YOUTUBE_URL_CONVERT,
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
        return DownloadMessage(chat_id, message_id, [d.case for d in diagnoses])
    if treatment == Treatment.YOUTUBE_URL_CONVERT:
        return YoutubeUrlConvertMessage(chat_id, message_id, [d.case for d in diagnoses])
    raise ValueError(f"Unkonown treatment: {treatment}")


def _handle_update(update: dict):
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

    # TODO: cut out the middle man
    messages = [
        _make_message(message["chat"]["id"], message["message_id"], treatment, diagnoses)
        for treatment, diagnoses in diagnosis_by_treatment.items()
    ]

    try:
        mqtt.publish_messages(messages)
    except Exception as e:
        _LOG.error("Could not publish events", exc_info=e)
        raise


def run():
    telegram.check()
    mqtt.check()

    received_sigterm = False

    def should_run() -> bool:
        return not received_sigterm

    def on_sigterm(*args):
        nonlocal received_sigterm
        received_sigterm = True

    signal.signal(signal.SIGTERM, on_sigterm)

    telegram.handle_updates(should_run, _handle_update)
