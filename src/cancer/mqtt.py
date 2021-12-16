import os
from typing import List, Callable, TypeVar

from paho.mqtt.publish import multiple
from paho.mqtt.subscribe import callback

from cancer.message import Message

_HOST = os.getenv("MQTT_HOST")
_USER = os.getenv("MQTT_USER")
_PASSWORD = os.getenv("MQTT_PASSWORD")


def check():
    if not (_HOST and _USER and _PASSWORD):
        raise ValueError("MQTT host, user or password is missing")


def publish_messages(messages: List[Message]):
    multiple(
        msgs=[
            dict(topic=message.topic(), payload=message.serialize())
            for message in messages
        ],
        hostname=_HOST,
        auth={"username": _USER, "password": _PASSWORD},
    )


T = TypeVar('T', bound=Message)


def subscribe(topic: str, handle: Callable[[T], None]):
    def on_message(client, userdata, message):
        payload = message.payload
        handle(T.deserialize(payload))

    callback(
        on_message,
        topics=[topic],
        qos=1,
        hostname=_HOST,
        auth={"username": _USER, "password": _PASSWORD},
    )
