from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo.errors import ConnectionFailure, DuplicateKeyError, ServerSelectionTimeoutError

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.models import ConfigurationRequest, FlightEvent, SimulationConfig
from app.ports import EventPublisher, Repository
from app.seed import example_configuration
from app.settings import Settings
from app.simulation import SimulationManager


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("Timestamp de vuelo inválido")


def _enriched_flight(flight: dict[str, Any]) -> dict[str, Any]:
    result = dict(flight)
    scheduled = _timestamp(result["scheduled_departure_at"])
    actual = _timestamp(result["actual_departure_at"])
    delay = (actual - scheduled).total_seconds() / 60
    threshold = int(result["delay_threshold_minutes"])
    result["delay_minutes"] = delay
    result["exceeds_threshold"] = delay > threshold
    return result


def _publish_seed(publisher_factory, config: SimulationConfig) -> None:
    """Publish the initial configuration on a best-effort basis.

    The API must keep serving MongoDB data even when Kafka is unavailable,
    so failures here are recorded as a warning and never abort startup.
    """
    publisher = None
    try:
        publisher = publisher_factory()
        publisher.publish_configuration(config)
    except Exception as error:  # noqa: BLE001 - startup must not depend on Kafka
        print(f"Aviso: no se pudo publicar la configuración inicial en Kafka: {error}")
    finally:
        if publisher is not None:
            close = getattr(publisher, "close", None)
            if close is not None:
                try:
                    close()
                except Exception as error:  # noqa: BLE001
                    print(f"Aviso: fallo al cerrar el productor del seed: {error}")


def create_app(
    repository: Repository | None = None,
    publisher_factory=None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings()
    if repository is None:
        from app.repository import MongoRepository

        repository = MongoRepository(
            settings.mongodb_uri,
            settings.mongodb_database,
            settings.mongodb_username,
            settings.mongodb_password,
        )
    if publisher_factory is None:
        from app.publisher import KafkaPublisher

        publisher_factory = lambda: KafkaPublisher(settings)

    manager = SimulationManager(repository, publisher_factory)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            ensure_indexes = getattr(repository, "ensure_indexes", None)
            if ensure_indexes is not None:
                await asyncio.to_thread(ensure_indexes)
            seed = example_configuration()
            await asyncio.to_thread(repository.ensure_seed, seed)
            await asyncio.to_thread(_publish_seed, publisher_factory, seed)
            yield
        finally:
            if manager.status.state in {"running", "stopping"}:
                await manager.stop()
            close = getattr(repository, "close", None)
            if close is not None:
                await asyncio.to_thread(close)

    app = FastAPI(title="AeroFlow Backend", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.repository = repository
    app.state.manager = manager

    @app.get("/health")
    async def health() -> dict[str, str]:
        try:
            await asyncio.to_thread(repository.list_configurations)
        except Exception as error:
            raise HTTPException(status_code=503, detail="MongoDB no disponible") from error
        return {"status": "ok"}

    @app.get("/api/configurations")
    async def list_configurations(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        configurations, total = await asyncio.to_thread(
            repository.list_configurations, offset, limit
        )
        return {
            "items": [config.model_dump(mode="json") for config in configurations],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/simulations")
    async def list_simulations(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        configurations, total = await asyncio.to_thread(
            repository.list_configurations, offset, limit
        )
        activity = await asyncio.to_thread(
            repository.simulation_activity,
            [config.simulation_id for config in configurations],
        )
        items = []
        for config in configurations:
            metrics = activity.get(config.simulation_id, {})
            items.append(
                {
                    "simulation_id": config.simulation_id,
                    "name": config.name,
                    "last_emitted_at": metrics.get("last_emitted_at"),
                    "stored_departures": metrics.get("stored_departures", 0),
                    "partial": manager.status.simulation_id == config.simulation_id
                    and manager.status.state in {"running", "stopping"},
                }
            )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/configurations/{simulation_id}")
    async def get_configuration(simulation_id: str) -> dict[str, Any]:
        config = await asyncio.to_thread(repository.get_configuration, simulation_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        return config.model_dump(mode="json")

    @app.post("/api/configurations", status_code=201)
    async def create_configuration(request: ConfigurationRequest) -> dict[str, Any]:
        payload = request.model_dump(mode="python")
        if request.simulation_id is not None:
            raise HTTPException(status_code=422, detail="simulation_id lo asigna el backend")
        payload["simulation_id"] = f"SIM-{uuid4().hex[:12].upper()}"
        payload["random_seed"] = (
            request.random_seed
            if request.random_seed is not None
            else secrets.randbits(64)
        )
        config = SimulationConfig.model_validate(payload)
        try:
            await asyncio.to_thread(repository.save_configuration, config)
        except DuplicateKeyError as error:
            raise HTTPException(
                status_code=409, detail="simulation_id ya existe"
            ) from error
        except (ServerSelectionTimeoutError, ConnectionFailure) as error:
            raise HTTPException(
                status_code=503, detail="MongoDB no disponible"
            ) from error
        return config.model_dump(mode="json")

    @app.get("/api/simulations/{simulation_id}/summary")
    async def summary(simulation_id: str) -> dict[str, Any]:
        config = await asyncio.to_thread(repository.get_configuration, simulation_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        events = await asyncio.to_thread(repository.flight_counts_by_gate, simulation_id)
        counts = {
            gate.gate_id: {"valid_departures": 0, "above_threshold": 0}
            for gate in config.gates
        }
        for raw in events:
            try:
                gate = raw["gate_id"]
                if gate not in counts:
                    continue
                counts[gate]["valid_departures"] = int(raw["valid_departures"])
                counts[gate]["above_threshold"] = int(raw["above_threshold"])
            except (KeyError, TypeError, ValueError):
                continue
        gates = []
        for gate in config.gates:
            metric = counts[gate.gate_id]
            metric["gate_id"] = gate.gate_id
            metric["name"] = gate.name
            metric["terminal_id"] = gate.terminal_id
            metric["delay_threshold_minutes"] = gate.delay_threshold_minutes
            metric["above_threshold_percentage"] = (
                metric["above_threshold"] / metric["valid_departures"] * 100
                if metric["valid_departures"]
                else 0.0
            )
            gates.append(metric)
        return {
            "simulation_id": simulation_id,
            "gates": gates,
            "partial": (
                manager.status.simulation_id == simulation_id
                and manager.status.state in {"running", "stopping"}
            ),
        }

    @app.get("/api/simulations/{simulation_id}/flights")
    async def latest_flights(
        simulation_id: str,
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        config = await asyncio.to_thread(repository.get_configuration, simulation_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        flights, total = await asyncio.to_thread(
            repository.list_flights, simulation_id, offset, limit
        )
        enriched = []
        for flight in flights:
            try:
                enriched.append(_enriched_flight(flight))
            except (KeyError, TypeError, ValueError):
                continue
        return {
            "simulation_id": simulation_id,
            "items": enriched,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/simulations/{simulation_id}/timeline")
    async def timeline(
        simulation_id: str,
        interval: str = Query(default="hour", pattern="^(hour|day)$"),
    ) -> dict[str, Any]:
        if await asyncio.to_thread(repository.get_configuration, simulation_id) is None:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        buckets = await asyncio.to_thread(repository.flights_over_time, simulation_id, interval)
        return {
            "simulation_id": simulation_id,
            "basis": "actual_departure_at",
            "timezone": "UTC",
            "interval": interval,
            "items": [
                {"timestamp": bucket.get("_id"), "departures": bucket.get("count", 0)}
                for bucket in buckets
            ],
        }

    @app.post("/api/simulations/{simulation_id}/start", status_code=202)
    async def start_simulation(simulation_id: str) -> dict[str, Any]:
        config = await asyncio.to_thread(repository.get_configuration, simulation_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        try:
            manager.start(config)
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            **manager.status.__dict__,
            "started_at": manager.status.started_at.isoformat()
            if manager.status.started_at
            else None,
        }

    @app.post("/api/simulations/stop")
    async def stop_simulation() -> dict[str, Any]:
        if manager.status.state not in {"running", "stopping"}:
            raise HTTPException(status_code=409, detail="No hay ninguna simulación activa")
        status = await manager.stop()
        return {
            **status.__dict__,
            "started_at": status.started_at.isoformat() if status.started_at else None,
            "finished_at": status.finished_at.isoformat() if status.finished_at else None,
        }

    @app.get("/api/simulations/status")
    def simulation_status() -> dict[str, Any]:
        status = manager.status
        return {
            **status.__dict__,
            "started_at": status.started_at.isoformat() if status.started_at else None,
            "finished_at": status.finished_at.isoformat() if status.finished_at else None,
        }

    @app.post("/api/simulations/{simulation_id}/test-events", status_code=202)
    async def publish_test_events(simulation_id: str) -> dict[str, Any]:
        config = await asyncio.to_thread(repository.get_configuration, simulation_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        publisher: EventPublisher = publisher_factory()
        gate = config.gates[0]
        examples = [
            (b"{invalid-json", "invalid_json"),
            (b'{"event_id":"missing-fields","record_valid":true}', "missing_fields"),
            (
                b'{"event_id":"explicit-invalid","record_valid":false}',
                "record_marked_invalid",
            ),
        ]
        try:
            for payload, case in examples:
                await asyncio.to_thread(publisher.publish_test_message, payload, case)
            duplicate = FlightEvent(
                event_id=f"EV-TEST-{simulation_id}",
                simulation_id=simulation_id,
                scheduled_departure_at=datetime.now(timezone.utc),
                actual_departure_at=datetime.now(timezone.utc),
                terminal_id=gate.terminal_id,
                gate_id=gate.gate_id,
                aircraft_id="AV-TEST",
                operation_id=f"OP-TEST-{simulation_id}",
                flight_number="TEST001",
                airline="Test Airline",
                aircraft_model="Test Model",
                destination_id=config.destinations[0].destination_id,
                delay_threshold_minutes=gate.delay_threshold_minutes,
            )
            duplicate_payload = duplicate.model_dump(mode="json", exclude={"quality_defects"})
            duplicate_payload["destination_id"] = config.destinations[0].destination_id
            duplicate_payload["record_valid"] = True
            encoded_duplicate = json.dumps(duplicate_payload).encode()
            await asyncio.to_thread(
            publisher.publish_test_message, encoded_duplicate, "duplicate_event"
            )
            await asyncio.to_thread(
                publisher.publish_test_message, encoded_duplicate, "duplicate_event"
            )
        finally:
            await asyncio.to_thread(publisher.close)
        return {
            "simulation_id": simulation_id,
            "messages": len(examples) + 2,
            "status": "published",
        }

    return app
