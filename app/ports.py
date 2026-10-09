from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.models import FlightEvent, SimulationConfig


class Repository(Protocol):
    def ensure_seed(self, config: SimulationConfig) -> None: ...

    def list_configurations(self) -> list[SimulationConfig]: ...

    def get_configuration(self, simulation_id: str) -> SimulationConfig | None: ...

    def save_configuration(self, config: SimulationConfig) -> None: ...

    def list_flights(
        self, simulation_id: str, skip: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]: ...

    def flight_counts_by_gate(self, simulation_id: str) -> list[dict[str, Any]]: ...

    def flights_over_time(
        self, simulation_id: str, interval: str
    ) -> list[dict[str, Any]]: ...


class EventPublisher(Protocol):
    def publish_configuration(self, config: SimulationConfig) -> None: ...

    def publish_event(self, event: FlightEvent) -> None: ...

    def publish_test_message(self, payload: bytes, case: str) -> None: ...

    def close(self) -> None: ...


class ApplicationServices(Protocol):
    repository: Repository
    publisher_factory: Any
    manager: Any
