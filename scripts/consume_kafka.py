from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from confluent_kafka import Consumer, KafkaError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import Settings


def main() -> None:
    settings = Settings()
    topics = sys.argv[1:] or [
        settings.kafka_configuration_topic,
        settings.kafka_flights_topic,
    ]
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "security.protocol": settings.kafka_security_protocol,
            "group.id": f"aeroflow-inspector-{uuid.uuid4().hex[:12]}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(topics)
    print(f"Escuchando: {', '.join(topics)}. Ctrl+C para salir.", flush=True)
    try:
        while True:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                if message.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"Error Kafka: {message.error()}", file=sys.stderr, flush=True)
                continue

            raw = message.value() or b""
            try:
                value = json.loads(raw)
                rendered = json.dumps(value, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, UnicodeDecodeError):
                rendered = repr(raw)
            headers = {
                name: value.decode("utf-8", errors="replace") if value else None
                for name, value in (message.headers() or [])
            }
            print(
                f"\n[{message.topic()} partition={message.partition()} "
                f"offset={message.offset()} key={message.key()!r}]\n"
                f"headers={headers}\n{rendered}",
                flush=True,
            )
    except KeyboardInterrupt:
        print("\nConsumidor detenido.", flush=True)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
