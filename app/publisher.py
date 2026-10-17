from __future__ import annotations

import json
import threading
import time
from typing import Any

from confluent_kafka import KafkaError, Producer

from app.models import FlightEvent, SimulationConfig
from app.settings import Settings


class KafkaPublisher:
    """Publica eventos en Kafka usando un pool de productores.

    Se mantienen varios clientes ``confluent_kafka.Producer`` (por defecto 5)
    que escriben en el **mismo topic**. Cada mensaje se envía, por turnos
    (round-robin), al siguiente productor del pool, repartiendo la carga de
    publicación entre todos ellos.

    La publicación es síncrona (espera la confirmación de Kafka antes de
    continuar), de modo que el orden de las llamadas se conserva aunque el
    mensaje viaje por productores distintos.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        producer_options = {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "security.protocol": settings.kafka_security_protocol,
            "message.timeout.ms": settings.kafka_delivery_timeout_seconds * 1000,
            "retries": settings.kafka_retries,
            "enable.idempotence": True,
        }
        if settings.kafka_ssl_ca_location:
            producer_options["ssl.ca.location"] = settings.kafka_ssl_ca_location

        self._producer_count = max(1, settings.kafka_producer_pool_size)
        self.producers: list[Producer] = []
        for index in range(self._producer_count):
            options = dict(producer_options)
            options["client.id"] = f"aeroflow-producer-{index + 1}"
            self.producers.append(Producer(options))
        self._next_index = 0
        self._lock = threading.Lock()

    def _next_producer(self) -> Producer:
        with self._lock:
            producer = self.producers[self._next_index]
            self._next_index = (self._next_index + 1) % self._producer_count
            return producer

    def publish_configuration(self, config: SimulationConfig) -> None:
        self._publish(
            topic=self.settings.kafka_configuration_topic,
            key=config.simulation_id,
            value=json.dumps(config.model_dump(mode="json"), separators=(",", ":")),
            headers=[
                ("message_type", b"configuration"),
                ("simulation_id", config.simulation_id.encode()),
            ],
        )

    def publish_event(self, event: FlightEvent) -> None:
        payload = event.model_dump(
            mode="json",
            exclude={"quality_defects", "wire_overrides", "wire_omissions"},
            exclude_none=True,
        )
        for field in event.wire_omissions:
            payload.pop(field, None)
        payload.update(event.wire_overrides)
        self._publish(
            topic=self.settings.kafka_flights_topic,
            key=event.aircraft_id,
            value=json.dumps(payload, separators=(",", ":")),
            headers=[
                ("message_type", b"flight"),
                ("simulation_id", event.simulation_id.encode()),
            ],
        )

    def publish_test_message(self, payload: bytes, case: str) -> None:
        self._publish(
            topic=self.settings.kafka_flights_topic,
            key=f"TEST-{case}",
            value=payload,
            headers=[("message_type", b"test"), ("test_case", case.encode())],
        )

    def _publish(self, **message: Any) -> None:
        producer = self._next_producer()
        last_error: KafkaError | None = None
        for attempt in range(self.settings.kafka_retries + 1):
            deadline = time.monotonic() + self.settings.kafka_delivery_timeout_seconds + 5
            delivered: list[KafkaError | None] = []

            def callback(error, _message):
                delivered.append(error)

            while True:
                try:
                    producer.produce(**message, on_delivery=callback)
                    break
                except BufferError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timeout esperando espacio en el buffer Kafka")
                    producer.poll(0.1)

            while not delivered:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timeout esperando confirmación de entrega Kafka")
                producer.poll(0.1)
            if delivered[0] is None:
                return
            last_error = delivered[0]
            if attempt < self.settings.kafka_retries:
                continue
        raise RuntimeError(f"Error al publicar en Kafka: {last_error}")

    def close(self) -> None:
        for producer in self.producers:
            producer.flush(self.settings.kafka_delivery_timeout_seconds)
