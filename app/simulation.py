from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.generator import generate_events
from app.models import SimulationConfig
from app.ports import EventPublisher, Repository


@dataclass
class SimulationStatus:
    state: str = "idle"
    simulation_id: str | None = None
    published: int = 0
    total: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None


class SimulationManager:
    def __init__(
        self, repository: Repository, publisher_factory: Callable[[], EventPublisher]
    ) -> None:
        self.repository = repository
        self.publisher_factory = publisher_factory
        self.status = SimulationStatus()
        self._stop_event: asyncio.Event | None = None
        self._task: asyncio.Task | None = None

    def start(self, config: SimulationConfig) -> SimulationStatus:
        if self.status.state in {"running", "stopping"}:
            raise RuntimeError("Ya hay una simulación activa")
        if self._task is not None and not self._task.done():
            raise RuntimeError("La ejecución anterior aún está finalizando")
        self.status = SimulationStatus(
            state="running",
            simulation_id=config.simulation_id,
            total=config.total_operations,
            started_at=datetime.now(timezone.utc),
        )
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(config, self._stop_event))
        return self.status

    async def stop(self) -> SimulationStatus:
        if self.status.state == "running" and self._stop_event is not None:
            self.status.state = "stopping"
            self._stop_event.set()
        if self._task is not None:
            await self._task
        return self.status

    async def wait(self) -> SimulationStatus:
        if self._task is not None:
            await self._task
        return self.status

    async def _run(self, config: SimulationConfig, stop_event: asyncio.Event) -> None:
        publisher: EventPublisher | None = None
        try:
            events = await asyncio.to_thread(generate_events, config)
            if stop_event.is_set():
                self.status.state = "stopped"
                return
            publisher = self.publisher_factory()
            await asyncio.to_thread(publisher.publish_configuration, config)
            for event in events:
                if stop_event.is_set():
                    self.status.state = "stopped"
                    break
                event.emitted_at = datetime.now(timezone.utc)
                await asyncio.to_thread(publisher.publish_event, event)
                self.status.published += 1
                if config.publish_interval_ms and not stop_event.is_set():
                    await self._wait_publish_interval(stop_event, config.publish_interval_ms)
            else:
                self.status.state = "completed"
        except Exception as error:
            self.status.state = "failed"
            self.status.last_error = str(error)
        finally:
            if publisher is not None:
                try:
                    await asyncio.to_thread(publisher.close)
                except Exception as error:
                    self.status.state = "failed"
                    self.status.last_error = str(error)
            self.status.finished_at = datetime.now(timezone.utc)

    @staticmethod
    async def _wait_publish_interval(stop_event: asyncio.Event, interval_ms: int) -> None:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_ms / 1000)
        except TimeoutError:
            return
