from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import SimulationConfig


class MemoryRepository:
    """Test adapter with the same small public boundary as the Mongo adapter."""

    def __init__(self) -> None:
        self.configurations: dict[str, SimulationConfig] = {}
        self.flights: list[dict[str, Any]] = []

    def ensure_seed(self, config: SimulationConfig) -> None:
        self.configurations.setdefault(config.simulation_id, config)

    def list_configurations(
        self, skip: int = 0, limit: int | None = None
    ) -> tuple[list[SimulationConfig], int]:
        ordered = sorted(self.configurations.values(), key=lambda item: item.simulation_id)
        page = ordered[skip:] if limit is None else ordered[skip : skip + limit]
        return page, len(ordered)

    def get_configuration(self, simulation_id: str) -> SimulationConfig | None:
        return self.configurations.get(simulation_id)

    def save_configuration(self, config: SimulationConfig) -> None:
        self.configurations[config.simulation_id] = config

    def simulation_activity(
        self, simulation_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        activity: dict[str, dict[str, Any]] = {}
        for flight in self.flights:
            simulation_id = flight.get("simulation_id")
            if simulation_id not in simulation_ids or flight.get("record_valid") is not True:
                continue
            entry = activity.setdefault(
                simulation_id, {"stored_departures": 0, "last_emitted_at": None}
            )
            entry["stored_departures"] += 1
            emitted_at = flight.get("emitted_at")
            if entry["last_emitted_at"] is None or _as_utc(emitted_at) >= _as_utc(
                entry["last_emitted_at"]
            ):
                entry["last_emitted_at"] = emitted_at
        return activity

    def list_flights(self, simulation_id: str, skip: int, limit: int):
        flights = [
            flight
            for flight in self.flights
            if flight["simulation_id"] == simulation_id
            and flight.get("record_valid") is True
        ]
        flights.sort(key=lambda flight: _as_utc(flight.get("emitted_at")), reverse=True)
        return flights[skip : skip + limit], len(flights)

    def flight_counts_by_gate(self, simulation_id: str) -> list[dict[str, Any]]:
        counts: dict[str, dict[str, int]] = {}
        for flight in self.flights:
            if flight["simulation_id"] != simulation_id or flight.get("record_valid") is not True:
                continue
            try:
                actual = flight["actual_departure_at"]
                scheduled = flight["scheduled_departure_at"]
                actual = _as_utc(actual)
                scheduled = _as_utc(scheduled)
                delay = (actual - scheduled).total_seconds() / 60
                threshold = float(flight["delay_threshold_minutes"])
                gate = flight["gate_id"]
            except (KeyError, TypeError, ValueError):
                continue
            count = counts.setdefault(gate, {"valid_departures": 0, "above_threshold": 0})
            count["valid_departures"] += 1
            count["above_threshold"] += int(delay > threshold)
        return [{"gate_id": gate, **metrics} for gate, metrics in counts.items()]

    def flights_over_time(self, simulation_id: str, interval: str) -> list[dict[str, Any]]:
        buckets: dict[str, int] = {}
        for flight in self.flights:
            if flight["simulation_id"] != simulation_id or flight.get("record_valid") is not True:
                continue
            timestamp = flight["actual_departure_at"]
            timestamp = _as_utc(timestamp)
            key = (
                timestamp.strftime("%Y-%m-%dT%H:00:00Z")
                if interval == "hour"
                else timestamp.strftime("%Y-%m-%dT00:00:00Z")
            )
            buckets[key] = buckets.get(key, 0) + 1
        return [{"_id": key, "count": count} for key, count in sorted(buckets.items())]


def _as_utc(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
