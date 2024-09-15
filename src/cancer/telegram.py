import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from httpx import Client, Response

_API_KEY = os.getenv("TELEGRAM_API_KEY")
_LOG = logging.getLogger(__name__)

_client = Client(timeout=60)


def check():
    if not _API_KEY:
        raise ValueError("Missing TELEGRAM_API_KEY")


def _build_url(method: str) -> str:
    return f"https://api.telegram.org/bot{_API_KEY}/{method}"


def _build_file_url(file_path: str) -> str:
    return f"https://api.telegram.org/file/bot{_API_KEY}/{file_path}"


def _get_actual_body(response: Response):
    response.raise_for_status()
    body = response.json()
    if body.get("ok"):
        return body["result"]
    raise ValueError(f"Body was not ok! {body}")


def _request_updates(last_update_id: int | None) -> list[dict]:
    body: dict | None = None
    if last_update_id:
        body = {
            "offset": last_update_id + 1,
            "timeout": 10,
        }
    return _get_actual_body(
        _client.post(
            _build_url("getUpdates"),
            json=body,
            timeout=12,
        )
    )


def handle_updates(should_run: Callable[[], bool], handler: Callable[[dict], None]):
    last_update_id: int | None = None
    while should_run():
        updates = _request_updates(last_update_id)
        try:
            for update in updates:
                _LOG.info(f"Received update: {update}")
                handler(update)
                last_update_id = update["update_id"]
        except Exception as e:
            _LOG.error("Could not handle update", exc_info=e)


def upload_video(
    chat_id: int | str,
    path: Path,
    reply_to_message_id: int | None,
    thumb_path: Path | None,
) -> dict:
    _LOG.info("Uploading file %s with thumb %s", path, thumb_path)
    url = _build_url("sendVideo")

    def _request(files: dict):
        return _client.post(
            url,
            data=dict(chat_id=chat_id, reply_to_message_id=reply_to_message_id),
            files=files,
        )

    response: Response
    with path.open("rb") as file:
        if thumb_path:
            with thumb_path.open("rb") as thumb_file:
                response = _request(dict(video=file, thumb=thumb_file))
                if response.status_code == 413:
                    _LOG.warning(
                        "Got Entity Too Large response, retrying without thumbnail"
                    )
                    return upload_video(chat_id, path, reply_to_message_id, None)
        else:
            response = _request(dict(video=file))

    return _get_actual_body(response)


def send_message(
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
) -> dict:
    return _get_actual_body(
        _client.post(
            _build_url("sendMessage"),
            json={
                "chat_id": chat_id,
                "reply_to_message_id": reply_to_message_id,
                "disable_notification": True,
                "allow_sending_without_reply": True,
                "disable_web_page_preview": True,
                "text": text,
            },
        )
    )


def download_file(file_id: str, file: IO[bytes]):
    response = _get_actual_body(
        _client.post(
            _build_url("getFile"),
            json={
                "file_id": file_id,
            },
        )
    )

    url = _build_file_url(response["file_path"])
    response = _client.get(url)
    response.raise_for_status()
    file.write(response.content)


def send_audio_message(
    chat_id: int,
    name: str,
    audio: IO[bytes],
    reply_to_message_id: int | None = None,
) -> dict:
    return _get_actual_body(
        _client.post(
            _build_url("sendDocument"),
            data={
                "chat_id": chat_id,
                "reply_to_message_id": reply_to_message_id,
                "disable_notification": True,
                "allow_sending_without_reply": True,
                "disable_web_page_preview": True,
                "disable_content_type_detection": True,
            },
            files=dict(document=(f"{name}.oga", audio)),
        )
    )


def send_video_group(
    chat_id: int,
    reply_to_message_id: int | None,
    videos: list[str],
) -> dict:
    return _get_actual_body(
        _client.post(
            _build_url("sendMediaGroup"),
            json={
                "chat_id": chat_id,
                "reply_to_message_id": reply_to_message_id,
                "disable_notification": True,
                "allow_sending_without_reply": True,
                "media": [
                    {
                        "type": "video",
                        "media": video_id,
                    }
                    for video_id in videos
                ],
            },
        )
    )


def set_message_reaction(
    *,
    chat_id: int,
    message_id: int,
    emoji: str | None,
) -> None:
    request_body: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
    }

    if emoji is not None:
        request_body["reaction"] = [
            {
                "type": "emoji",
                "emoji": emoji,
            }
        ]
    _get_actual_body(
        _client.post(
            _build_url("setMessageReaction"),
            json=request_body,
        )
    )
