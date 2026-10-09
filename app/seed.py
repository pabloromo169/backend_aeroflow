from datetime import datetime, timezone

from app.models import SimulationConfig


def example_configuration() -> SimulationConfig:
    airlines = [{"airline": f"Aero{i:02d}", "flight_prefix": f"A{i:02d}"} for i in range(1, 11)]
    models = [
        {"model_id": f"MODEL-{i:02d}", "name": f"Modelo {chr(64 + i)}"}
        for i in range(1, 6)
    ]
    aircraft = [
        {
            "aircraft_id": f"AV-{i:04d}",
            "airline": airlines[(i - 1) // 5]["airline"],
            "aircraft_model": models[((i - 1) // 5) % len(models)]["name"],
        }
        for i in range(1, 51)
    ]
    return SimulationConfig.model_validate(
        {
            "simulation_id": "SIM-01",
            "name": "Aeropuerto simulado Bahía de Cádiz",
            "timezone": "Europe/Madrid",
            "simulation_start": datetime(2026, 10, 5, tzinfo=timezone.utc),
            "simulation_days": 7,
            "publish_interval_ms": 100,
            "random_seed": 42,
            "total_operations": 1060,
            "defect_rate": 0.05,
            "destinations": [
                {"destination_id": "DEST-01", "name": "Destino Norte"},
                {"destination_id": "DEST-02", "name": "Destino Centro"},
                {"destination_id": "DEST-03", "name": "Destino Este"},
                {"destination_id": "DEST-04", "name": "Destino Sur"},
            ],
            "gates": [
                {
                    "gate_id": f"G{i}",
                    "name": f"Puerta {i}",
                    "terminal_id": f"T{i}",
                    "delay_threshold_minutes": 15 if i != 4 else 20,
                }
                for i in range(1, 6)
            ],
            "airlines": airlines,
            "aircraft_models": models,
            "aircraft": aircraft,
            "generation_profiles": {
                "base_delay_probability": 0.24,
                "gate_volume_weights": {"G1": 1.2, "G5": 0.8},
                "destination_volume_weights": {"DEST-03": 1.3},
                "time_band_volume_weights": {"morning": 1.2, "night": 0.75},
                "gate_delay_multipliers": {"G4": 2.0},
                "destination_delay_multipliers": {"DEST-02": 1.5},
                "time_band_delay_multipliers": {"evening": 1.7},
                "max_delay_minutes_beyond_threshold": 60,
            },
        }
    )
