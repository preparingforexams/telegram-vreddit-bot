from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from ssl import SSLContext
from threading import Thread
from typing import Callable, Type

import pika
from pika import PlainCredentials, BasicProperties
from pika.adapters.blocking_connection import BlockingChannel
from pika.connection import Parameters, SSLOptions

from cancer.message import Message, Topic
from cancer.port.publisher import Publisher
from cancer.port.subscriber import Subscriber, T

_LOG = logging.getLogger(__name__)


@dataclass
class RabbitConfig:
    host: str
    virtual_host: str
    port: int
    use_ssl: bool
    exchange: str
    user: str
    password: str

    @property
    def parameters(self) -> Parameters:
        params = Parameters()
        params.host = self.host
        params.port = self.port
        params.virtual_host = self.virtual_host
        params.ssl_options = SSLOptions(SSLContext()) if self.use_ssl else None
        params.credentials = PlainCredentials(self.user, self.password)
        params.heartbeat = 30
        return params

    @staticmethod
    def _get_required(key: str, allow_empty: bool = False) -> str:
        result = os.getenv(key)

        if result or (allow_empty and result is not None):
            return result

        raise ValueError(f"Missing key: {key}")

    @classmethod
    def from_env(cls) -> RabbitConfig:
        return cls(
            host=cls._get_required("RABBITMQ_HOST"),
            virtual_host=cls._get_required("RABBITMQ_VIRTUAL_HOST"),
            port=int(cls._get_required("RABBITMQ_PORT")),
            exchange=cls._get_required("RABBITMQ_EXCHANGE", allow_empty=True),
            use_ssl=cls._get_required("RABBITMQ_USE_TLS") == "true",
            user=cls._get_required("RABBITMQ_USER"),
            password=cls._get_required("RABBITMQ_PASSWORD"),
        )


class RabbitPublisher(Publisher):
    def __init__(self, config: RabbitConfig):
        self.config = config

    @contextmanager
    def _connect(self) -> pika.BlockingConnection:
        connection = pika.BlockingConnection(self.config.parameters)
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _channel(self):
        with self._connect() as connection:
            channel = connection.channel()
            try:
                yield channel
            finally:
                channel.close()

    def publish(self, topic: Topic, message: Message):
        with self._channel() as channel:
            channel.basic_publish(
                exchange=self.config.exchange,
                routing_key=topic.value,
                body=message.serialize(),
                properties=BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
                )
            )
        _LOG.info("Published message to RabbitMQ queue %s", topic.value)


class _Heartbeat:
    def __init__(self, connection):
        self._connection = connection
        self._is_running = False

    def start(self):
        if self._is_running:
            raise ValueError("Already running")

        self._is_running = True
        Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self._is_running:
            self._connection.process_data_events()
            time.sleep(10)

    def stop(self):
        self._is_running = False


class RabbitSubscriber(Subscriber):
    def __init__(self, config: RabbitConfig):
        self.config = config

    def subscribe(self, topic: Topic, message_type: Type[T], handle: Callable[[T], Subscriber.Result]):
        def _callback(channel: BlockingChannel, method, _, message: bytes):
            try:
                deserialized = message_type.deserialize(message)
            except ValueError as e:
                _LOG.error("Could not deserialize message", exc_info=e)
                channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
                return

            heartbeat = _Heartbeat(channel.connection)
            heartbeat.start()

            try:
                result = handle(deserialized)
            except Exception as e:
                _LOG.error("Unexpected exception", exc_info=e)
                channel.basic_nack(method.delivery_tag, requeue=True)
                return

            heartbeat.stop()

            if result == Subscriber.Result.Ack:
                channel.basic_ack(delivery_tag=method.delivery_tag)
            elif result == Subscriber.Result.Drop:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            elif result == Subscriber.Result.Drop:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        connection = pika.BlockingConnection(self.config.parameters)
        channel = connection.channel()
        try:
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=topic.value,
                on_message_callback=_callback,
                auto_ack=False,
            )
            channel.start_consuming()
        finally:
            if not channel.is_closed:
                channel.close()
            if not connection.is_closed:
                connection.close()
