import logging
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Callable, Optional, List
from urllib.parse import urlparse

import requests
from yt_dlp import YoutubeDL

_API_KEY = os.getenv("TELEGRAM_API_KEY")
_STORAGE_DIR = os.getenv("STORAGE_DIR", "downloads")
_UPLOAD_CHAT = os.getenv("UPLOAD_CHAT_ID", "133399998")

_LOG = logging.getLogger("vredditbot")

_CANCER_HOSTS = [
    "v.redd.it",
]


@dataclass
class Cure:
    cure_path: str
    cancer: str


@dataclass
class Drug:
    drug_id: str
    cancer: str


def _build_url(method: str) -> str:
    return f"https://api.telegram.org/bot{_API_KEY}/{method}"


def _get_actual_body(response: requests.Response):
    response.raise_for_status()
    body = response.json()
    if body.get("ok"):
        return body["result"]
    raise ValueError(f"Body was not ok! {body}")


def _upload_video(path: str) -> dict:
    _LOG.info("Uploading file %s", path)
    url = _build_url("sendVideo")
    with open(path, 'rb') as file:
        response = requests.post(
            url,
            data=dict(chat_id=_UPLOAD_CHAT),
            files=dict(video=file),
        )

    return _get_actual_body(response)


def _build_input_media_video(drug: Drug) -> dict:
    return {
        "type": "video",
        "media": drug.drug_id,
    }


def _send_drug_package(
    chat_id: int,
    reply_to_message_id: Optional[int],
    drugs: List[Drug],
) -> dict:
    return _get_actual_body(requests.post(
        _build_url("sendMediaGroup"),
        json={
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
            "disable_notification": True,
            "media": [_build_input_media_video(drug) for drug in drugs]
        },
        timeout=10,
    ))


def _diagnose_cancer(text: str, entity: dict) -> Optional[str]:
    if entity["type"] == "url":
        offset = entity["offset"]
        length = entity["length"]
        url = text[offset:offset + length]
    elif entity["type"] == "text_link":
        url = entity["url"]
    else:
        return None

    _LOG.info("Extracted URL %s", url)
    netloc = urlparse(url).netloc
    if any(netloc.startswith(cancer_host) for cancer_host in _CANCER_HOSTS):
        return url


def _develop_cures(cancer: str) -> List[Cure]:
    if not os.path.exists(_STORAGE_DIR):
        os.mkdir(_STORAGE_DIR)

    cure_id = str(uuid.uuid4())
    cure_dir = os.path.join(_STORAGE_DIR, cure_id)
    os.mkdir(cure_dir)

    ytdl = YoutubeDL(params={
        "outtmpl": f"{cure_dir}/output%(autonumber)d.%(ext)s",
    })

    return_code = ytdl.download([cancer])
    if not return_code == 0:
        _LOG.error("YTDL returned error code %d", return_code)
        return []

    cure_names = os.listdir(cure_dir)
    _LOG.debug("Downloaded files %s", cure_names)

    return [
        Cure(
            cure_path=os.path.join(cure_dir, cure_name),
            cancer=cancer,
        )
        for cure_name in cure_names
    ]


def _manufacture_drug(cure: Cure) -> Drug:
    message = _upload_video(cure.cure_path)
    video = message["video"]
    file_id = video["file_id"]
    return Drug(cancer=cure.cancer, drug_id=file_id)


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

    cancers = []
    for entity in entities:
        cancer = _diagnose_cancer(text, entity)
        if cancer:
            cancers.append(cancer)

    if not cancers:
        _LOG.debug("Message was healthy")
        return

    cures = [cure for cancer in cancers for cure in _develop_cures(cancer)]
    drugs = [_manufacture_drug(cure) for cure in cures]

    _send_drug_package(
        chat_id=message["chat"]["id"],
        reply_to_message_id=message["message_id"],
        drugs=drugs
    )


def _request_updates(last_update_id: Optional[int]) -> List[dict]:
    body: Optional[dict] = None
    if last_update_id:
        body = {
            "offset": last_update_id + 1
        }
    return _get_actual_body(requests.post(
        _build_url("getUpdates"),
        json=body,
    ))


def _handle_updates(handler: Callable[[dict], None]):
    last_update_id: Optional[int] = None
    while True:
        updates = _request_updates(last_update_id)
        try:
            for update in updates:
                _LOG.info(f"Received update: {update}")
                handler(update)
                last_update_id = update["update_id"]
        except Exception as e:
            _LOG.error("Could not handle update", exc_info=e)


def _setup_logging():
    logging.basicConfig()
    _LOG.level = logging.INFO


def main():
    _setup_logging()

    if not _API_KEY:
        _LOG.error("Missing API key")
        sys.exit(1)

    _handle_updates(_handle_update)


if __name__ == '__main__':
    main()
