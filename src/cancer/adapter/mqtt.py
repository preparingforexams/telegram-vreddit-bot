from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Type, Callable, Optional, Dict

from cancer.message import Message, Topic
from cancer.port.publisher import Publisher
from cancer.port.subscriber import Subscriber, T
from paho.mqtt.publish import single
from paho.mqtt.subscribe import callback

_LOG = logging.getLogger(__name__)


@dataclass
class MqttConfig:
    host: str
    port: int
    user: str
    password: str
    use_tls: bool
    transport: Optional[str] = None

    @property
    def effective_transport(self) -> str:
        return self.transport or "tcp"

    @property
    def auth(self) -> Dict[str, str]:
        return {"username": self.user, "password": self.password}

    @staticmethod
    def _get_required(key: str) -> str:
        result = os.getenv(key)
        if not result:
            raise ValueError(f"Missing key: {key}")
        return result

    @classmethod
    def from_env(cls) -> MqttConfig:
        return cls(
            host=cls._get_required("MQTT_HOST"),
            port=int(cls._get_required("MQTT_PORT")),
            user=cls._get_required("MQTT_USER"),
            password=cls._get_required("MQTT_PASSWORD"),
            use_tls=cls._get_required("MQTT_TLS_ENABLE") == "true",
            transport=os.getenv("MQTT_TRANSPORT"),
        )


@dataclass
class MqttPublisher(Publisher):
    config: MqttConfig

    def publish(self, topic: Topic, message: Message):
        _LOG.debug("Publishing message %s", message)
        single(
            qos=1,
            topic=f"cancer/{topic.value}",
            payload=message.serialize(),
            hostname=self.config.host,
            port=self.config.port,
            transport=self.config.effective_transport,
            auth=self.config.auth,
            tls={} if self.config.use_tls else None,
        )


@dataclass
class MqttSubscriber(Subscriber):
    config: MqttConfig

    def subscribe(
        self,
        topic: Topic,
        message_type: Type[T],
        handle: Callable[[T], Subscriber.Result],
    ):
        def on_message(client, userdata, message):
            payload = message.payload
            _LOG.debug("Received message with payload %s", payload)
            handle(message_type.deserialize(payload))

        callback(
            on_message,
            topics=[topic.value],
            qos=1,
            hostname=self.config.host,
            port=self.config.port,
            transport=self.config.effective_transport,
            auth=self.config.auth,
            tls={} if self.config.use_tls else None,
        )
