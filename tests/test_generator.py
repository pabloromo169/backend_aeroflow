from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.generator import generate_events
from app.seed import example_configuration


def test_generation_is_reproducible_except_for_real_emission_timestamp():
    config = example_configuration()

    first = generate_events(config)
    second = generate_events(config)

    assert len(first) == 1060
    assert [event.model_copy(update={"emitted_at": None}) for event in first] == [
        event.model_copy(update={"emitted_at": None}) for event in second
    ]


def test_events_obey_flight_identity_ordering_and_quality_contract():
    events = generate_events(example_configuration())

    published_departures = [
        datetime.fromisoformat(
            event.wire_overrides.get(
                "actual_departure_at", event.actual_departure_at.isoformat()
            ).replace("Z", "+00:00")
        )
        for event in events
    ]
    assert published_departures == sorted(published_departures)
    assert len({event.event_id for event in events}) == len(events)
    assert len({event.operation_id for event in events}) == len(events)
    assert all(event.record_valid is True for event in events)
    assert sum(not event.passes_quality_checks for event in events) == 53

    scheduled_by_aircraft: dict[str, list] = {}
    for event in events:
        scheduled_by_aircraft.setdefault(event.aircraft_id, []).append(event)
    for aircraft_events in scheduled_by_aircraft.values():
        aircraft_events.sort(key=lambda event: event.scheduled_departure_at)
        for previous, current in zip(aircraft_events, aircraft_events[1:]):
            assert previous.scheduled_departure_at < current.scheduled_departure_at
            assert previous.actual_departure_at < current.scheduled_departure_at


def test_company_samples_remain_above_the_analytic_minimum():
    events = generate_events(example_configuration())
    counts: dict[str, int] = {}
    for event in events:
        if event.passes_quality_checks:
            counts[event.airline] = counts.get(event.airline, 0) + 1

    assert len(counts) == 10
    assert min(counts.values()) >= 100


def test_company_model_groups_have_100_valid_observations_for_analytic_cutoff():
    events = generate_events(example_configuration())
    counts: dict[tuple[str, str], int] = {}
    for event in events:
        if event.passes_quality_checks:
            group = (event.airline, event.aircraft_model)
            counts[group] = counts.get(group, 0) + 1

    assert len(counts) == 10
    assert min(counts.values()) >= 100


def test_defective_records_remain_identifiable_in_test_metadata_without_wire_fields():
    events = generate_events(example_configuration())
    assert all(event.record_valid for event in events)
    assert sum(bool(event.quality_defects) for event in events) == 53


def test_generated_schedule_covers_all_seven_days_and_time_bands():
    events = generate_events(example_configuration())
    local = [
        event.scheduled_departure_at.astimezone(ZoneInfo("Europe/Madrid"))
        for event in events
    ]

    assert len({timestamp.date() for timestamp in local}) >= 7
    assert {timestamp.hour // 6 for timestamp in local} == {0, 1, 2, 3}


def test_delayed_departures_that_cross_the_simulated_period_are_included():
    config = example_configuration().model_copy(update={"simulation_days": 7})
    config.generation_profiles.base_delay_probability = 1.0
    config.generation_profiles.max_delay_minutes_beyond_threshold = 1440

    events = generate_events(config)
    local_end = config.simulation_start.astimezone(ZoneInfo(config.timezone))
    local_end += timedelta(days=config.simulation_days)

    assert any(
        event.scheduled_departure_at.astimezone(ZoneInfo(config.timezone)) < local_end
        and event.actual_departure_at.astimezone(ZoneInfo(config.timezone)) >= local_end
        for event in events
    )


def test_defective_payload_overrides_are_not_leaked_to_configuration_or_event_contract():
    event = next(
        event
        for event in generate_events(example_configuration())
        if event.wire_omissions
    )

    assert event.destination_id
    assert "destination_id" in event.wire_omissions
    assert "wire_omissions" not in event.model_dump()


def test_defect_fraction_is_fixed_exactly_and_distributed_across_period():
    events = generate_events(example_configuration())

    assert sum(not event.passes_quality_checks for event in events) == 53
    assert len(
        {
            event.scheduled_departure_at.date()
            for event in events
            if not event.passes_quality_checks
        }
    ) == 7
