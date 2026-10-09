import asyncio
from datetime import datetime

from app.memory import MemoryRepository
from app.seed import example_configuration
from app.simulation import SimulationManager


class RecordingPublisher:
    def __init__(self):
        self.configuration = None
        self.events = []
        self.closed = False

    def publish_configuration(self, config):
        self.configuration = config

    def publish_event(self, event):
        self.events.append(event)

    def publish_test_message(self, payload, case):
        pass

    def close(self):
        self.closed = True


def test_simulation_publishes_config_then_ordered_events_and_reports_progress():
    publisher = RecordingPublisher()
    manager = SimulationManager(MemoryRepository(), lambda: publisher)
    config = example_configuration()
    object.__setattr__(config, "total_operations", 1060)
    object.__setattr__(config, "publish_interval_ms", 0)

    async def scenario():
        manager.start(config)
        return await manager.wait()

    status = asyncio.run(scenario())

    assert publisher.configuration.simulation_id == config.simulation_id
    published = [
        datetime.fromisoformat(
            event.wire_overrides.get("actual_departure_at", event.actual_departure_at.isoformat()).replace(
                "Z", "+00:00"
            )
        )
        for event in publisher.events
    ]
    assert published == sorted(published)
    assert status.state == "completed"
    assert status.published == status.total == 1060
    assert publisher.closed


def test_stop_is_orderly_between_confirmed_events():
    publisher = RecordingPublisher()
    manager = SimulationManager(MemoryRepository(), lambda: publisher)
    config = example_configuration()
    object.__setattr__(config, "total_operations", 1060)
    object.__setattr__(config, "publish_interval_ms", 10)

    async def scenario():
        manager.start(config)
        while manager.status.published < 2:
            await asyncio.sleep(0)
        return await manager.stop()

    status = asyncio.run(scenario())

    assert status.state == "stopped"
    assert status.published == len(publisher.events) == 2
    assert publisher.closed


def test_stop_during_generation_does_not_publish_after_stop_request():
    publisher = RecordingPublisher()
    manager = SimulationManager(MemoryRepository(), lambda: publisher)
    config = example_configuration()

    async def scenario():
        manager.start(config)
        await asyncio.sleep(0)
        return await manager.stop()

    status = asyncio.run(scenario())

    assert status.state == "stopped"
    assert publisher.configuration is None
    assert publisher.events == []
