from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.api import create_app
from app.memory import MemoryRepository
from app.seed import example_configuration


class NullPublisher:
    messages = []

    def publish_configuration(self, config):
        pass

    def publish_event(self, event):
        pass

    def publish_test_message(self, payload, case):
        self.messages.append((payload, case))

    def close(self):
        pass


def test_configuration_creation_assigns_unique_id_and_seed():
    repository = MemoryRepository()
    repository.ensure_seed(example_configuration())
    app = create_app(repository=repository, publisher_factory=NullPublisher)
    client = TestClient(app)
    payload = example_configuration().model_dump(mode="json", exclude={"simulation_id", "random_seed"})

    first = client.post("/api/configurations", json=payload)
    second = client.post("/api/configurations", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["simulation_id"] != second.json()["simulation_id"]
    assert first.json()["random_seed"] != second.json()["random_seed"]


def test_unknown_configuration_cannot_start_simulation():
    app = create_app(repository=MemoryRepository(), publisher_factory=NullPublisher)
    response = TestClient(app).post("/api/simulations/UNKNOWN/start")

    assert response.status_code == 404


def test_summary_includes_empty_gates_and_uses_strict_threshold_comparison():
    repository = MemoryRepository()
    config = example_configuration()
    repository.ensure_seed(config)
    repository.flights.extend(
        [
            {
                "simulation_id": config.simulation_id,
                "gate_id": "G1",
                "scheduled_departure_at": "2026-10-05T08:00:00Z",
                "actual_departure_at": "2026-10-05T08:15:00Z",
                "delay_threshold_minutes": 15,
                "record_valid": True,
            },
            {
                "simulation_id": config.simulation_id,
                "gate_id": "G1",
                "scheduled_departure_at": "2026-10-05T09:00:00Z",
                "actual_departure_at": "2026-10-05T09:16:00Z",
                "delay_threshold_minutes": 15,
                "record_valid": True,
            },
        ]
    )
    response = TestClient(create_app(repository=repository, publisher_factory=NullPublisher)).get(
        f"/api/simulations/{config.simulation_id}/summary"
    )

    assert response.status_code == 200
    assert len(response.json()["gates"]) == 5
    assert response.json()["gates"][0]["valid_departures"] == 2
    assert response.json()["gates"][0]["above_threshold"] == 1
    assert response.json()["gates"][1]["valid_departures"] == 0


def test_summary_counts_valid_records_only():
    repository = MemoryRepository()
    config = example_configuration()
    repository.ensure_seed(config)
    repository.flights.extend(
        [
            {
                "simulation_id": config.simulation_id,
                "gate_id": "G1",
                "scheduled_departure_at": "2026-10-05T08:00:00Z",
                "actual_departure_at": "2026-10-05T08:20:00Z",
                "delay_threshold_minutes": 15,
                "record_valid": False,
            },
            {
                "simulation_id": config.simulation_id,
                "gate_id": "G1",
                "scheduled_departure_at": "2026-10-05T08:00:00Z",
                "actual_departure_at": "2026-10-05T08:20:00Z",
                "delay_threshold_minutes": 15,
                "record_valid": True,
            },
        ]
    )
    response = TestClient(create_app(repository=repository, publisher_factory=NullPublisher)).get(
        f"/api/simulations/{config.simulation_id}/summary"
    )

    assert response.json()["gates"][0]["valid_departures"] == 1
    assert response.json()["gates"][0]["above_threshold"] == 1


def test_timeline_groups_actual_departure_timestamps_by_utc_hour():
    repository = MemoryRepository()
    config = example_configuration()
    repository.ensure_seed(config)
    repository.flights.extend(
        [
            {
                "simulation_id": config.simulation_id,
                "actual_departure_at": "2026-10-05T08:03:00Z",
                "record_valid": True,
            },
            {
                "simulation_id": config.simulation_id,
                "actual_departure_at": "2026-10-05T08:57:00Z",
                "record_valid": True,
            },
            {
                "simulation_id": config.simulation_id,
                "actual_departure_at": "2026-10-05T09:00:00Z",
                "record_valid": True,
            },
        ]
    )
    response = TestClient(create_app(repository=repository, publisher_factory=NullPublisher)).get(
        f"/api/simulations/{config.simulation_id}/timeline?interval=hour"
    )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"timestamp": "2026-10-05T08:00:00Z", "departures": 2},
        {"timestamp": "2026-10-05T09:00:00Z", "departures": 1},
    ]


def test_configurations_assign_random_seed_unless_one_is_provided():
    repository = MemoryRepository()
    repository.ensure_seed(example_configuration())
    client = TestClient(create_app(repository=repository, publisher_factory=NullPublisher))
    payload = example_configuration().model_dump(
        mode="json", exclude={"simulation_id", "random_seed"}
    )

    generated = client.post("/api/configurations", json=payload).json()
    payload["random_seed"] = 987654
    reproducible = client.post("/api/configurations", json=payload).json()

    assert generated["random_seed"] != 987654
    assert reproducible["random_seed"] == 987654
    assert generated["simulation_id"] != reproducible["simulation_id"]


def test_creation_rejects_client_supplied_simulation_id():
    repository = MemoryRepository()
    repository.ensure_seed(example_configuration())
    payload = example_configuration().model_dump(mode="json")

    response = TestClient(create_app(repository=repository, publisher_factory=NullPublisher)).post(
        "/api/configurations", json=payload
    )

    assert response.status_code == 422


def test_test_events_send_the_same_duplicate_payload_twice():
    repository = MemoryRepository()
    config = example_configuration()
    repository.ensure_seed(config)
    NullPublisher.messages.clear()

    response = TestClient(create_app(repository=repository, publisher_factory=NullPublisher)).post(
        f"/api/simulations/{config.simulation_id}/test-events"
    )

    duplicates = [payload for payload, case in NullPublisher.messages if case == "duplicate_event"]
    assert response.status_code == 202
    assert len(duplicates) == 2
    assert duplicates[0] == duplicates[1]


def test_latest_flights_are_limited_and_exclude_records_marked_invalid():
    repository = MemoryRepository()
    config = example_configuration()
    repository.ensure_seed(config)
    for index in range(3):
        repository.flights.append(
            {
                "simulation_id": config.simulation_id,
                "event_id": f"EV-{index}",
                "emitted_at": f"2026-10-05T08:0{index}:00Z",
                "scheduled_departure_at": "2026-10-05T08:00:00Z",
                "actual_departure_at": f"2026-10-05T08:0{index}:00Z",
                "delay_threshold_minutes": 15,
                "record_valid": index != 2,
            }
        )
    response = TestClient(create_app(repository=repository, publisher_factory=NullPublisher)).get(
        f"/api/simulations/{config.simulation_id}/flights?limit=1"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["event_id"] == "EV-1"


def test_latest_flights_calculates_delay_and_exceedance_from_stored_timestamps():
    repository = MemoryRepository()
    config = example_configuration()
    repository.ensure_seed(config)
    repository.flights.append(
        {
            "simulation_id": config.simulation_id,
            "event_id": "EV-CALC",
            "emitted_at": "2026-10-05T08:30:00Z",
            "scheduled_departure_at": "2026-10-05T08:00:00Z",
            "actual_departure_at": "2026-10-05T08:25:30Z",
            "delay_threshold_minutes": 25,
            "record_valid": True,
        }
    )

    response = TestClient(create_app(repository=repository, publisher_factory=NullPublisher)).get(
        f"/api/simulations/{config.simulation_id}/flights"
    )

    assert response.json()["items"][0]["delay_minutes"] == 25.5
    assert response.json()["items"][0]["exceeds_threshold"] is True


def test_health_reports_mongodb_query_failures():
    class UnavailableRepository(MemoryRepository):
        def list_configurations(self):
            raise RuntimeError("database unavailable")

    response = TestClient(
        create_app(repository=UnavailableRepository(), publisher_factory=NullPublisher)
    ).get("/health")

    assert response.status_code == 503
    assert response.json()["detail"] == "MongoDB no disponible"


def test_creation_maps_mongodb_connection_failures_to_service_unavailable():
    class UnavailableRepository(MemoryRepository):
        def save_configuration(self, config):
            raise ServerSelectionTimeoutError("server selection timed out")

    repository = UnavailableRepository()
    repository.ensure_seed(example_configuration())
    payload = example_configuration().model_dump(
        mode="json", exclude={"simulation_id", "random_seed"}
    )

    response = TestClient(
        create_app(repository=repository, publisher_factory=NullPublisher)
    ).post("/api/configurations", json=payload)

    assert response.status_code == 503


def test_configuration_list_is_paginated():
    repository = MemoryRepository()
    seed = example_configuration()
    repository.ensure_seed(seed)
    for suffix in range(3):
        config = seed.model_copy(update={"simulation_id": f"SIM-PAGE-{suffix}"})
        repository.save_configuration(config)
    client = TestClient(create_app(repository=repository, publisher_factory=NullPublisher))

    response = client.get("/api/configurations?limit=2&offset=1")

    assert response.status_code == 200
    assert response.json()["total"] == 4
    assert len(response.json()["items"]) == 2
    assert response.json()["limit"] == 2


def test_simulation_selector_includes_only_count_and_latest_timestamp():
    repository = MemoryRepository()
    config = example_configuration()
    repository.ensure_seed(config)
    repository.flights.append(
        {
            "simulation_id": config.simulation_id,
            "event_id": "EV-LATEST",
            "emitted_at": "2026-10-05T08:00:00Z",
            "scheduled_departure_at": "2026-10-05T08:00:00Z",
            "actual_departure_at": "2026-10-05T08:20:00Z",
            "delay_threshold_minutes": 15,
            "record_valid": True,
        }
    )

    response = TestClient(create_app(repository=repository, publisher_factory=NullPublisher)).get(
        "/api/simulations"
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["simulation_id"] == config.simulation_id
    assert item["stored_departures"] == 1
    assert item["last_emitted_at"] == "2026-10-05T08:00:00Z"
