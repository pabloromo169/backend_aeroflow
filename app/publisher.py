from __future__ import annotations

import json
import time
from typing import Any

from confluent_kafka import KafkaError, Producer

from app.models import FlightEvent, SimulationConfig
from app.settings import Settings


class KafkaPublisher:
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
        self.producer = Producer(producer_options)

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
        last_error: KafkaError | None = None
        for attempt in range(self.settings.kafka_retries + 1):
            deadline = time.monotonic() + self.settings.kafka_delivery_timeout_seconds + 5
            delivered: list[KafkaError | None] = []

            def callback(error, _message):
                delivered.append(error)

            while True:
                try:
                    self.producer.produce(**message, on_delivery=callback)
                    break
                except BufferError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timeout esperando espacio en el buffer Kafka")
                    self.producer.poll(0.1)

            while not delivered:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timeout esperando confirmación de entrega Kafka")
                self.producer.poll(0.1)
            if delivered[0] is None:
                return
            last_error = delivered[0]
            if attempt < self.settings.kafka_retries:
                continue
        raise RuntimeError(f"Error al publicar en Kafka: {last_error}")

    def close(self) -> None:
        self.producer.flush(self.settings.kafka_delivery_timeout_seconds)
