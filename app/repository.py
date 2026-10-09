from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient

from app.models import SimulationConfig


class MongoRepository:
    def __init__(
        self,
        uri: str,
        database: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.client = MongoClient(
            uri,
            username=username or None,
            password=password or None,
            serverSelectionTimeoutMS=5000,
            tz_aware=True,
        )
        self.database = self.client[database]
        self.configurations = self.database["operativos"]
        self.flights = self.database["vuelos"]

    def ensure_indexes(self) -> None:
        self.client.admin.command("ping")
        self.configurations.create_index([("simulation_id", ASCENDING)], unique=True)
        self.flights.create_index([("event_id", ASCENDING)], unique=True)
        self.flights.create_index([("simulation_id", ASCENDING), ("emitted_at", DESCENDING)])
        self.flights.create_index([("simulation_id", ASCENDING), ("gate_id", ASCENDING)])
        self.flights.create_index([("simulation_id", ASCENDING), ("terminal_id", ASCENDING)])
        self.flights.create_index(
            [("simulation_id", ASCENDING), ("scheduled_departure_at", ASCENDING)]
        )
        self.flights.create_index([("simulation_id", ASCENDING), ("aircraft_id", ASCENDING)])
        self.flights.create_index(
            [("simulation_id", ASCENDING), ("actual_departure_at", ASCENDING)]
        )

    def ensure_seed(self, config: SimulationConfig) -> None:
        self.configurations.update_one(
            {"simulation_id": config.simulation_id},
            {"$setOnInsert": config.model_dump(mode="python")},
            upsert=True,
        )

    def list_configurations(self) -> list[SimulationConfig]:
        return [
            SimulationConfig.model_validate(self._without_id(document))
            for document in self.configurations.find().sort("simulation_id", ASCENDING)
        ]

    def get_configuration(self, simulation_id: str) -> SimulationConfig | None:
        document = self.configurations.find_one({"simulation_id": simulation_id})
        return SimulationConfig.model_validate(self._without_id(document)) if document else None

    def save_configuration(self, config: SimulationConfig) -> None:
        self.configurations.insert_one(config.model_dump(mode="python"))

    def list_flights(self, simulation_id: str, skip: int, limit: int):
        query = {"simulation_id": simulation_id, "record_valid": True}
        cursor = (
            self.flights.find(query, {"_id": 0})
            .sort("emitted_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        return list(cursor), self.flights.count_documents(query)

    def flight_counts_by_gate(self, simulation_id: str) -> list[dict[str, Any]]:
        delay_minutes = {
            "$divide": [
                {"$subtract": ["$actual_departure_at", "$scheduled_departure_at"]},
                60_000,
            ]
        }
        return list(
            self.flights.aggregate(
                [
                    {"$match": {"simulation_id": simulation_id, "record_valid": True}},
                    {
                        "$group": {
                            "_id": "$gate_id",
                            "valid_departures": {"$sum": 1},
                            "above_threshold": {
                                "$sum": {
                                    "$cond": [
                                        {"$gt": [delay_minutes, "$delay_threshold_minutes"]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "gate_id": "$_id",
                            "valid_departures": 1,
                            "above_threshold": 1,
                        }
                    },
                ]
            )
        )

    def flights_over_time(self, simulation_id: str, interval: str) -> list[dict[str, Any]]:
        date_format = {"hour": "%Y-%m-%dT%H:00:00Z", "day": "%Y-%m-%dT00:00:00Z"}[interval]
        return list(
            self.flights.aggregate(
                [
                    {"$match": {"simulation_id": simulation_id, "record_valid": True}},
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": date_format,
                                    "date": "$actual_departure_at",
                                    "timezone": "UTC",
                                }
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id": ASCENDING}},
                ]
            )
        )

    @staticmethod
    def _without_id(document: dict | None) -> dict | None:
        if document is None:
            return None
        document.pop("_id", None)
        return document

    def close(self) -> None:
        self.client.close()
