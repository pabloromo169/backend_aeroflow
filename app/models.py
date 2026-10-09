from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


NonEmpty = Annotated[str, Field(min_length=1)]


class Destination(BaseModel):
    destination_id: NonEmpty
    name: NonEmpty


class Gate(BaseModel):
    gate_id: Literal["G1", "G2", "G3", "G4", "G5"]
    name: NonEmpty
    terminal_id: Literal["T1", "T2", "T3", "T4", "T5"]
    delay_threshold_minutes: int = Field(ge=0)


class Airline(BaseModel):
    airline: NonEmpty
    flight_prefix: Annotated[str, Field(min_length=2, max_length=3)]


class AircraftModel(BaseModel):
    model_id: NonEmpty
    name: NonEmpty


class Aircraft(BaseModel):
    aircraft_id: NonEmpty
    airline: NonEmpty
    aircraft_model: NonEmpty


class GenerationProfiles(BaseModel):
    base_delay_probability: float = Field(default=0.25, ge=0, le=1)
    gate_volume_weights: dict[str, float] = Field(default_factory=dict)
    destination_volume_weights: dict[str, float] = Field(default_factory=dict)
    time_band_volume_weights: dict[str, float] = Field(default_factory=dict)
    gate_delay_multipliers: dict[str, float] = Field(default_factory=dict)
    destination_delay_multipliers: dict[str, float] = Field(default_factory=dict)
    time_band_delay_multipliers: dict[str, float] = Field(default_factory=dict)
    max_delay_minutes_beyond_threshold: int = Field(default=60, ge=1, le=1440)

    @field_validator(
        "gate_volume_weights",
        "destination_volume_weights",
        "time_band_volume_weights",
    )
    @classmethod
    def volume_weights_must_be_positive(cls, value: dict[str, float]) -> dict[str, float]:
        if any(weight <= 0 for weight in value.values()):
            raise ValueError("Los pesos de volumen deben ser positivos")
        return value

    @field_validator(
        "gate_delay_multipliers",
        "destination_delay_multipliers",
        "time_band_delay_multipliers",
    )
    @classmethod
    def delay_multipliers_must_be_valid(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not 0 <= multiplier <= 4 for multiplier in value.values()):
            raise ValueError("Los multiplicadores deben estar entre 0 y 4")
        return value


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_id: NonEmpty = "PENDING"
    name: NonEmpty
    timezone: str = "Europe/Madrid"
    simulation_start: datetime
    simulation_days: int = Field(default=7, ge=7, le=31)
    publish_interval_ms: int = Field(default=100, ge=0, le=60_000)
    random_seed: int = Field(default=0, ge=0)
    total_operations: int = Field(default=1060, ge=100, le=100_000)
    defect_rate: Literal[0.05] = 0.05
    destinations: list[Destination] = Field(min_length=1)
    gates: list[Gate] = Field(min_length=5, max_length=5)
    airlines: list[Airline] = Field(min_length=1)
    aircraft_models: list[AircraftModel] = Field(min_length=1)
    aircraft: list[Aircraft] = Field(min_length=1)
    generation_profiles: GenerationProfiles = Field(default_factory=GenerationProfiles)

    @field_validator("simulation_start")
    @classmethod
    def start_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("simulation_start debe incluir zona horaria")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_airport_configuration(self) -> SimulationConfig:
        if self.simulation_id == "PENDING":
            raise ValueError("simulation_id debe ser asignado por el backend")
        if self.timezone != "Europe/Madrid":
            raise ValueError("El escenario utiliza Europe/Madrid")
        if {gate.gate_id for gate in self.gates} != {f"G{i}" for i in range(1, 6)}:
            raise ValueError("Deben existir exactamente las puertas G1-G5")
        if {gate.terminal_id for gate in self.gates} != {f"T{i}" for i in range(1, 6)}:
            raise ValueError("Cada puerta debe estar asociada a un terminal T1-T5")
        if len({gate.terminal_id for gate in self.gates}) != 5:
            raise ValueError("La asignación entre puertas y terminales debe ser uno a uno")
        if len({gate.gate_id for gate in self.gates}) != 5:
            raise ValueError("No se pueden repetir puertas")
        destination_ids = {destination.destination_id for destination in self.destinations}
        if len(destination_ids) != len(self.destinations):
            raise ValueError("destination_id debe ser único")
        if len({airline.airline for airline in self.airlines}) != len(self.airlines):
            raise ValueError("Los nombres de compañía deben ser únicos")
        if len({airline.flight_prefix for airline in self.airlines}) != len(self.airlines):
            raise ValueError("Los prefijos de vuelo deben ser únicos")
        if len({aircraft.aircraft_id for aircraft in self.aircraft}) != len(self.aircraft):
            raise ValueError("aircraft_id debe ser único")
        airline_names = {airline.airline for airline in self.airlines}
        model_names = {model.name for model in self.aircraft_models}
        if any(plane.airline not in airline_names for plane in self.aircraft):
            raise ValueError("Cada avión debe referenciar una compañía del catálogo")
        if airline_names - {plane.airline for plane in self.aircraft}:
            raise ValueError("Cada compañía debe tener al menos un avión en la flota")
        aircraft_counts = {
            name: sum(plane.airline == name for plane in self.aircraft)
            for name in airline_names
        }
        if max(aircraft_counts.values()) - min(aircraft_counts.values()) > 1:
            raise ValueError("La flota debe repartirse equilibradamente entre compañías")
        if any(plane.aircraft_model not in model_names for plane in self.aircraft):
            raise ValueError("Cada avión debe referenciar un modelo del catálogo")
        gate_ids = {gate.gate_id for gate in self.gates}
        if set(self.generation_profiles.gate_volume_weights) - gate_ids:
            raise ValueError("Hay perfiles de volumen para puertas desconocidas")
        if set(self.generation_profiles.destination_volume_weights) - destination_ids:
            raise ValueError("Hay perfiles de volumen para destinos desconocidos")
        if set(self.generation_profiles.gate_delay_multipliers) - gate_ids:
            raise ValueError("Hay perfiles de retraso para puertas desconocidas")
        if set(self.generation_profiles.destination_delay_multipliers) - destination_ids:
            raise ValueError("Hay perfiles de retraso para destinos desconocidos")
        time_bands = {"night", "morning", "afternoon", "evening"}
        if set(self.generation_profiles.time_band_volume_weights) - time_bands:
            raise ValueError("Hay perfiles de volumen para franjas desconocidas")
        if set(self.generation_profiles.time_band_delay_multipliers) - time_bands:
            raise ValueError("Hay perfiles de retraso para franjas desconocidas")
        defect_count = int(self.total_operations * self.defect_rate + 0.5)
        min_company_count = self.total_operations // len(airline_names)
        max_defects_per_company = (
            defect_count + len(airline_names) - 1
        ) // len(airline_names)
        if min_company_count - max_defects_per_company < 100:
            raise ValueError(
                "La configuración necesita al menos 100 salidas válidas estimadas por compañía"
            )
        return self


class ConfigurationRequest(SimulationConfig):
    """Configuration input where the API owns the simulation ID and seed default."""

    simulation_id: str | None = Field(default=None, exclude=True)
    random_seed: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def provide_server_generated_placeholders(cls, value: dict) -> dict:
        data = dict(value)
        if not data.get("simulation_id"):
            data.pop("simulation_id", None)
        if data.get("random_seed") is None:
            data.pop("random_seed", None)
        return data


class FlightEvent(BaseModel):
    event_id: str
    schema_version: Literal[1] = 1
    simulation_id: str
    scheduled_departure_at: datetime
    actual_departure_at: datetime
    emitted_at: datetime | None = None
    terminal_id: str
    gate_id: str
    aircraft_id: str
    operation_id: str
    flight_number: str
    airline: str
    aircraft_model: str
    destination_id: str
    delay_threshold_minutes: int
    record_valid: Literal[True] = True
    quality_defects: list[str] = Field(default_factory=list, exclude=True)
    wire_overrides: dict[str, object] = Field(default_factory=dict, exclude=True)
    wire_omissions: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def timestamps_must_be_aware(self) -> FlightEvent:
        if self.scheduled_departure_at.tzinfo is None or self.actual_departure_at.tzinfo is None:
            raise ValueError("Las horas de salida deben incluir zona horaria")
        if self.emitted_at is not None and self.emitted_at.tzinfo is None:
            raise ValueError("emitted_at debe incluir zona horaria")
        return self

    @property
    def delay_minutes(self) -> float:
        return (self.actual_departure_at - self.scheduled_departure_at).total_seconds() / 60

    @property
    def passes_quality_checks(self) -> bool:
        return not self.quality_defects
