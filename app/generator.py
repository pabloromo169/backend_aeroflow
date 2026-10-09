from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models import FlightEvent, SimulationConfig


TIME_BANDS = ("night", "morning", "afternoon", "evening")
LOCAL_TZ = ZoneInfo("Europe/Madrid")


def _weighted_choice(rng: random.Random, values: list[tuple[str, float]]) -> str:
    population, weights = zip(*values)
    return rng.choices(population, weights=weights, k=1)[0]


def _profile_weight(overrides: dict[str, float], key: str) -> float:
    return overrides.get(key, 1.0)


def _time_band(local_hour: int) -> str:
    if local_hour < 6:
        return "night"
    if local_hour < 12:
        return "morning"
    if local_hour < 18:
        return "afternoon"
    return "evening"


def _minute_in_band(rng: random.Random, band: str) -> int:
    start_hour = {"night": 0, "morning": 6, "afternoon": 12, "evening": 18}[band]
    return start_hour * 60 + rng.randrange(360)


def _schedule_for_aircraft(
    rng: random.Random,
    config: SimulationConfig,
    aircraft_id: str,
    count: int,
    operation_ids: list[int],
    defect_kinds: dict[int, int],
) -> list[FlightEvent]:
    plane = next(plane for plane in config.aircraft if plane.aircraft_id == aircraft_id)
    airline = next(airline for airline in config.airlines if airline.airline == plane.airline)
    profile = config.generation_profiles
    start = config.simulation_start
    local_start = start.astimezone(LOCAL_TZ)
    events: list[FlightEvent] = []

    candidates: list[tuple[datetime, str, int, int]] = []
    for offset, operation_id in enumerate(operation_ids):
        day_index = min(
            config.simulation_days - 1,
            offset * config.simulation_days // max(1, count),
        )
        band = _weighted_choice(
            rng,
            [
                (name, _profile_weight(profile.time_band_volume_weights, name))
                for name in TIME_BANDS
            ],
        )
        local_day = (local_start + timedelta(days=day_index)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        scheduled = (local_day + timedelta(minutes=_minute_in_band(rng, band))).astimezone(timezone.utc)
        candidates.append((scheduled, band, day_index, operation_id))
    candidates.sort(key=lambda candidate: candidate[0])
    last_scheduled = start

    for scheduled, band, day_index, event_index in candidates:
        scheduled = max(start, last_scheduled, scheduled)
        gate = _weighted_choice(
            rng,
            [
                (gate.gate_id, _profile_weight(profile.gate_volume_weights, gate.gate_id))
                for gate in config.gates
            ],
        )
        destination_id = _weighted_choice(
            rng,
            [
                (
                    destination.destination_id,
                    _profile_weight(profile.destination_volume_weights, destination.destination_id),
                )
                for destination in config.destinations
            ],
        )
        gate_config = next(
            gate_config for gate_config in config.gates if gate_config.gate_id == gate
        )
        terminal_id = gate_config.terminal_id
        event_threshold = gate_config.delay_threshold_minutes
        band = _time_band(scheduled.astimezone(LOCAL_TZ).hour)
        probability = profile.base_delay_probability
        for override in (
            profile.gate_delay_multipliers.get(gate, 1.0),
            profile.destination_delay_multipliers.get(destination_id, 1.0),
            profile.time_band_delay_multipliers.get(band, 1.0),
        ):
            probability *= override
        probability = min(1.0, probability)

        if rng.random() < probability:
            delay = gate_config.delay_threshold_minutes + rng.randint(
                1, profile.max_delay_minutes_beyond_threshold
            )
        else:
            delay = rng.randint(0, gate_config.delay_threshold_minutes)
        actual = scheduled + timedelta(minutes=delay)
        reserved_actual = actual
        defects: list[str] = []
        wire_overrides: dict[str, object] = {}
        wire_omissions: list[str] = []
        if event_index in defect_kinds:
            defect_kind = defect_kinds[event_index]
            if defect_kind == 0:
                defects.append("missing_required_field:destination_id")
                wire_omissions.append("destination_id")
            elif defect_kind == 1:
                defects.append("unknown_destination_id")
                destination_id = "DEST-UNKNOWN"
            elif defect_kind == 2:
                defects.append("negative_delay_threshold")
                event_threshold = -1
            else:
                defects.append("recorded_actual_before_scheduled")
                wire_overrides["actual_departure_at"] = (
                    scheduled - timedelta(minutes=1)
                ).isoformat().replace("+00:00", "Z")
        defects.sort()
        operation_id = f"OP-{config.simulation_id}-{event_index:06d}"
        event = FlightEvent(
            event_id=f"EV-{config.simulation_id}-{event_index:06d}",
            simulation_id=config.simulation_id,
            scheduled_departure_at=scheduled,
            actual_departure_at=reserved_actual,
            terminal_id=terminal_id,
            gate_id=gate,
            aircraft_id=aircraft_id,
            operation_id=operation_id,
            flight_number=f"{airline.flight_prefix}{100 + event_index % 900}",
            airline=airline.airline,
            aircraft_model=plane.aircraft_model,
            destination_id=(
                "DEST-01"
                if "missing_required_field:destination_id" in defects
                else destination_id
            ),
            delay_threshold_minutes=event_threshold,
            quality_defects=defects,
            wire_overrides=wire_overrides,
            wire_omissions=wire_omissions,
        )
        events.append(event)
        last_scheduled = actual + timedelta(minutes=35)
    return events


def generate_events(config: SimulationConfig) -> list[FlightEvent]:
    """Generate deterministic flight records for a simulation configuration."""
    if config.total_operations < 100:
        raise ValueError("La simulación requiere al menos 100 operaciones")
    seed = config.random_seed
    rng = random.Random(seed)
    defect_count = int(config.total_operations * config.defect_rate + 0.5)
    defect_rng = random.Random(seed ^ 0xA3F10)
    airline_names = sorted(airline.airline for airline in config.airlines)
    per_company, remainder = divmod(config.total_operations, len(airline_names))
    defects_per_company, companies_with_extra_defect = divmod(
        defect_count, len(airline_names)
    )
    defect_kinds: dict[int, int] = {}
    aircraft = sorted(config.aircraft, key=lambda plane: plane.aircraft_id)
    counts_by_airline = {
        name: per_company + (1 if index < remainder else 0)
        for index, name in enumerate(airline_names)
    }
    by_company: dict[str, list] = {name: [] for name in airline_names}
    for plane in aircraft:
        by_company[plane.airline].append(plane)

    generated: list[FlightEvent] = []
    global_ordinal = 0
    for company_index, company in enumerate(airline_names):
        fleet = by_company[company]
        total = counts_by_airline[company]
        each, extra = divmod(total, len(fleet))
        company_start = global_ordinal + 1
        company_operation_ids = list(range(company_start, company_start + total))
        company_defect_count = defects_per_company + int(
            company_index < companies_with_extra_defect
        )
        company_defect_indices = set(defect_rng.sample(company_operation_ids, company_defect_count))
        for defect_index in sorted(company_defect_indices):
            defect_kinds[defect_index] = len(defect_kinds) % 4
        for plane_index, plane in enumerate(fleet):
            count = each + (1 if plane_index < extra else 0)
            begin = plane_index * each + min(plane_index, extra)
            operation_ids = company_operation_ids[begin : begin + count]
            generated.extend(
                _schedule_for_aircraft(
                    rng,
                    config,
                    plane.aircraft_id,
                    count,
                    operation_ids,
                    defect_kinds,
                )
            )
        global_ordinal += total
    def published_departure(event: FlightEvent) -> datetime:
        overridden = event.wire_overrides.get("actual_departure_at")
        if isinstance(overridden, str):
            return datetime.fromisoformat(overridden.replace("Z", "+00:00"))
        return event.actual_departure_at

    generated.sort(key=lambda event: (published_departure(event), event.event_id))
    last_effective_by_aircraft: dict[str, datetime] = {}
    for event in generated:
        effective = published_departure(event)
        previous_effective = last_effective_by_aircraft.get(event.aircraft_id)
        if previous_effective is not None and event.scheduled_departure_at <= previous_effective:
            shift = previous_effective + timedelta(minutes=35) - event.scheduled_departure_at
            event.scheduled_departure_at += shift
            event.actual_departure_at += shift
            if isinstance(event.wire_overrides.get("actual_departure_at"), str):
                event.wire_overrides["actual_departure_at"] = (
                    effective + shift
                ).isoformat().replace("+00:00", "Z")
            effective += shift
        last_effective_by_aircraft[event.aircraft_id] = effective
    generated.sort(key=lambda event: (published_departure(event), event.event_id))
    # A fixed RNG-derived emission timestamp allows exact reproduction in
    # fixtures. The live publisher replaces it with the real UTC publication time.
    for event in generated:
        event.emitted_at = datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(
            seconds=int(event.event_id.rsplit("-", 1)[-1])
        )
    return generated
