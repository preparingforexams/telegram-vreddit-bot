import logging
import os
import random
import sys
from typing import Callable, Optional, List

import requests

_API_KEY = os.getenv("TELEGRAM_API_KEY")

_LOG = logging.getLogger("coinbot")


def _build_url(method: str) -> str:
    return f"https://api.telegram.org/bot{_API_KEY}/{method}"


def _get_actual_body(response: requests.Response):
    response.raise_for_status()
    body = response.json()
    if body.get("ok"):
        return body["result"]
    raise ValueError(f"Body was not ok! {body}")


def _send_message(chat_id: int, text: str, reply_to_message_id: Optional[int]) -> dict:
    return _get_actual_body(requests.post(
        _build_url("sendMessage"),
        json={
            "text": text,
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
        },
        timeout=10,
    ))


def _handle_update(update: dict):
    message = update.get("message")

    if not message:
        _LOG.debug("Skipping non-message update")
        return

    text: Optional[str] = message.get("text")
    if not text:
        _LOG.debug("Skipping non-text message")
        return

    if not text.startswith("/flip"):
        _LOG.debug("Skipping non-flip message")
        return

    result = bool(random.getrandbits(1))
    result_text = "heads" if result else "tails"

    _send_message(
        chat_id=message["chat"]["id"],
        text=f"The results are in and it's {result_text}",
        reply_to_message_id=message["message_id"]
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
