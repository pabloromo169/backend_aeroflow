import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "consume_kafka.py"


def _load_consumer_module():
    spec = importlib.util.spec_from_file_location("consume_kafka", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSettings:
    kafka_bootstrap_servers = "broker:443"
    kafka_security_protocol = "SSL"
    kafka_ssl_ca_location = "C:/certs/ca.pem"
    kafka_flights_topic = "aeroflow.vuelos"
    kafka_configuration_topic = "aeroflow.configuracion"


def test_inspector_consumer_receives_the_private_ca(monkeypatch):
    module = _load_consumer_module()
    captured = {}

    class FakeConsumer:
        def __init__(self, options):
            captured.update(options)

        def subscribe(self, topics):
            pass

        def poll(self, timeout):
            raise KeyboardInterrupt

        def close(self):
            pass

    monkeypatch.setattr(module, "Settings", _FakeSettings)
    monkeypatch.setattr(module, "Consumer", FakeConsumer)
    monkeypatch.setattr(sys, "argv", ["consume_kafka.py"])

    module.main()

    assert captured["bootstrap.servers"] == "broker:443"
    assert captured["security.protocol"] == "SSL"
    assert captured["ssl.ca.location"] == "C:/certs/ca.pem"


def test_inspector_consumer_omits_ca_when_not_configured(monkeypatch):
    module = _load_consumer_module()
    captured = {}

    class SettingsWithoutCa(_FakeSettings):
        kafka_ssl_ca_location = None

    class FakeConsumer:
        def __init__(self, options):
            captured.update(options)

        def subscribe(self, topics):
            pass

        def poll(self, timeout):
            raise KeyboardInterrupt

        def close(self):
            pass

    monkeypatch.setattr(module, "Settings", SettingsWithoutCa)
    monkeypatch.setattr(module, "Consumer", FakeConsumer)
    monkeypatch.setattr(sys, "argv", ["consume_kafka.py"])

    module.main()

    assert "ssl.ca.location" not in captured
