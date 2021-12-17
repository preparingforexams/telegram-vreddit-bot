import logging
import os
from typing import List, Callable, TypeVar, Type

from paho.mqtt.publish import multiple
from paho.mqtt.subscribe import callback

from cancer.message import Message

_LOG = logging.getLogger(__name__)

_HOST = os.getenv("MQTT_HOST")
_PORT = os.getenv("MQTT_PORT")
_USER = os.getenv("MQTT_USER")
_PASSWORD = os.getenv("MQTT_PASSWORD")
_TRANSPORT = os.getenv("MQTT_TRANSPORT", "tcp")


def check():
    if not (_HOST and _PORT and _USER and _PASSWORD and _TRANSPORT):
        raise ValueError("MQTT host, port, user or password is missing")
    int(_PORT)

    _LOG.debug("Going to use %s transport", _TRANSPORT)


def publish_messages(messages: List[Message]):
    _LOG.debug("Publishing messages %s", messages)
    multiple(
        msgs=[
            dict(topic=message.topic(), qos=1, payload=message.serialize())
            for message in messages
        ],
        hostname=_HOST,
        port=int(_PORT),
        transport=_TRANSPORT,
        auth={"username": _USER, "password": _PASSWORD},
        tls={},
    )


T = TypeVar('T', bound=Message)


def subscribe(message_type: Type[T], handle: Callable[[T], None]):
    def on_message(client, userdata, message):
        payload = message.payload
        _LOG.debug("Received message with payload %s", payload)
        handle(message_type.deserialize(payload))

    callback(
        on_message,
        topics=[message_type.topic()],
        qos=1,
        hostname=_HOST,
        port=int(_PORT),
        transport=_TRANSPORT,
        auth={"username": _USER, "password": _PASSWORD},
        tls={},
    )
