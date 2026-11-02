# Guía: simulación dedicada de evidencia post-fin (`SIM-POSTEND`)

Guía paso a paso para demostrar, con datos reales en MongoDB y consultables desde
Dremio, que el simulador incluye operaciones **programadas dentro del periodo** cuya
salida efectiva cae **después del fin del periodo simulado**.

La simulación `SIM-POSTEND` es **solo evidencia**. No forma parte del análisis
principal de `SIM-01`; el informe de Power BI debe seguir filtrando por `SIM-01`.

- **Simulación:** `SIM-POSTEND`
- **Periodo:** `2026-10-05` a `2026-10-12` (7 días, `Europe/Madrid`)
- **Objetivo:** generar retrasos altos para que alguna salida cruce el fin del periodo
- **Dependencias:** backend, Kafka, NiFi, MongoDB y Dremio ya operativos

---

## 1. Por qué una simulación aparte

`SIM-01` es la simulación de análisis y tiene retrasos moderados. Si se aumentara su
probabilidad de retraso, cambiarían todos los resultados D1–D9 y se perdería la
comparación documentada. Por eso la evidencia post-fin se obtiene con una simulación
pequeña e independiente:

- no se toca `SIM-01`;
- no se alteran las cifras del informe;
- el caso queda almacenado y es consultable con SQL;
- el rechazo de defectos sigue activo (5 %).

---

## 2. Configuración utilizada

La configuración se basa en el catálogo de `SIM-01`, pero se reduce a una compañía y
cinco aviones para que la evidencia sea pequeña y clara.

| Parámetro | Valor |
|---|---|
| `simulation_id` | `SIM-POSTEND` |
| `name` | `Evidencia de salidas posteriores al periodo` |
| `simulation_start` | `2026-10-05T00:00:00Z` |
| `simulation_days` | `7` |
| `publish_interval_ms` | `0` (publicación rápida) |
| `random_seed` | `0` |
| `total_operations` | `106` |
| `defect_rate` | `0.05` (fijo) |
| Compañías | `Aero01` |
| Aviones | `AV-0001` … `AV-0005` |
| Modelos | `Modelo A` |
| Destinos | `DEST-01` … `DEST-04` |
| `base_delay_probability` | `1.0` (todos los válidos superan el umbral) |
| `max_delay_minutes_beyond_threshold` | `1440` (hasta 24 h de exceso) |

Con 106 operaciones y un 5 % de defectos se generan **5 defectos** y **101 salidas
válidas**, por encima del mínimo de 100 por compañía que exige el modelo.

### 2.1. Creación de la configuración

La API asigna un `simulation_id` aleatorio a las configuraciones creadas desde el
formulario. Para que la evidencia use un identificador estable se inserta el documento
directamente en `operativos` con el modelo del backend:

```python
from app.models import SimulationConfig
from app.seed import example_configuration
from app.settings import Settings
from pymongo import MongoClient

base = example_configuration().model_dump(mode="python")
data = dict(base)
data.update(
    {
        "simulation_id": "SIM-POSTEND",
        "name": "Evidencia de salidas posteriores al periodo",
        "publish_interval_ms": 0,
        "random_seed": 0,
        "total_operations": 106,
        "airlines": base["airlines"][:1],
        "aircraft_models": base["aircraft_models"][:1],
        "aircraft": base["aircraft"][:5],
    }
)
data["generation_profiles"] = dict(base["generation_profiles"])
data["generation_profiles"]["base_delay_probability"] = 1.0
data["generation_profiles"]["max_delay_minutes_beyond_threshold"] = 1440
config = SimulationConfig.model_validate(data)

settings = Settings()
client = MongoClient(
    settings.mongodb_uri,
    username=settings.mongodb_username or None,
    password=settings.mongodb_password or None,
    serverSelectionTimeoutMS=10000,
    tz_aware=True,
)
db = client[settings.mongodb_database]
db.operativos.delete_many({"simulation_id": "SIM-POSTEND"})
db.vuelos.delete_many({"simulation_id": "SIM-POSTEND"})
db.operativos.insert_one(config.model_dump(mode="python"))
print("configuración guardada")
```

> El catálogo de destinos es fijo (`DEST-01`…`DEST-04`) y coincide con la lista de
> `ClasificarVuelo` en NiFi. La API y el modelo rechazan cualquier otro catálogo.

---

## 3. Ejecución

Con el backend en marcha:

```bash
curl -X POST http://127.0.0.1:8000/api/simulations/SIM-POSTEND/start
curl http://127.0.0.1:8000/api/simulations/status
```

Con `publish_interval_ms = 0` la publicación termina en pocos segundos. Después hay
que esperar a que NiFi consuma y guarde los documentos:

```bash
ssh hadoop@192.168.0.26 \
  '/opt/kafka/bin/kafka-consumer-groups.sh \
     --bootstrap-server localhost:9092 \
     --group aeroflow-vuelos --describe'
```

Resultado esperado: `LAG 0`.

### 3.1. Comprobación en MongoDB

```javascript
const db = db.getSiblingDB("aeroflow");
print("SIM-POSTEND:", db.vuelos.countDocuments({simulation_id: "SIM-POSTEND"}));
print("DEST-UNKNOWN:", db.vuelos.countDocuments({
  simulation_id: "SIM-POSTEND",
  destination_id: "DEST-UNKNOWN"
}));
print("por destino:", db.vuelos.aggregate([
  {$match: {simulation_id: "SIM-POSTEND"}},
  {$group: {_id: "$destination_id", n: {$sum: 1}}},
  {$sort: {_id: 1}}
]).toArray());
```

Resultado obtenido:

```text
SIM-POSTEND: 101
DEST-UNKNOWN: 0
por destino:
  DEST-01, DEST-02, DEST-03, DEST-04
```

Los 5 defectos (2 campos ausentes, 1 destino desconocido, 1 umbral negativo y 1 salida
efectiva anterior) se rechazan en NiFi. La cola acumulada del Funnel queda en
**16** `ValidarEsquemaVuelo → invalid` y **42** `ClasificarVuelo → invalidos`:
14 + 39 de `SIM-01` y 2 + 3 de `SIM-POSTEND`.

---

## 4. Evidencia de cruce del fin del periodo

Consulta sobre `V0_salidas` (Dremio o el mismo SQL en MongoDB):

```sql
SELECT event_id, gate_id, destination_id,
       scheduled_departure_at, actual_departure_at,
       delay_minutes, delay_threshold_minutes
FROM Aeroflow.V0_salidas
WHERE simulation_id = 'SIM-POSTEND'
  AND scheduled_departure_at < TIMESTAMP '2026-10-12 00:00:00'
  AND actual_departure_at >= TIMESTAMP '2026-10-12 00:00:00'
ORDER BY actual_departure_at;
```

Resultado real:

| `event_id` | Puerta | Destino | Salida programada | Salida efectiva | Retraso | Umbral |
|---|---|---|---|---|---|---|
| `EV-SIM-POSTEND-000033` | G2 | DEST-02 | 2026-10-11 10:50 | 2026-10-12 00:01 | 791 min | 15 |
| `EV-SIM-POSTEND-000078` | G1 | DEST-03 | 2026-10-11 15:01 | 2026-10-12 02:20 | 679 min | 15 |
| `EV-SIM-POSTEND-000100` | G2 | DEST-02 | 2026-10-11 22:37 | 2026-10-12 20:37 | 1320 min | 15 |

Las tres operaciones están **programadas antes** del fin (`2026-10-12 00:00`) y su
salida efectiva es **posterior**. Es la evidencia que se pedía; no se ha modificado
`SIM-01`.

### 4.1. Totales de la simulación

```sql
SELECT COUNT(*) AS valid_departures,
       COUNT(DISTINCT aircraft_id) AS distinct_aircraft,
       SUM(exceeds_threshold) AS over_threshold
FROM Aeroflow.V0_salidas
WHERE simulation_id = 'SIM-POSTEND';
```

Resultado:

```text
valid_departures = 101
distinct_aircraft = 5
over_threshold = 101
```

Todos los válidos superan el umbral porque `base_delay_probability = 1.0`. Es
intencionado: el objetivo es forzar el cruce del fin, no analizar esta simulación.

---

## 5. Estado global tras la evidencia

| Colección | Documentos |
|---|---:|
| `vuelos` de `SIM-01` | 1.007 |
| `vuelos` de `SIM-NIFI-TEST` | 1 |
| `vuelos` de `SIM-POSTEND` | 101 |
| **Total `vuelos`** | **1.109** |
| `operativos` | 4 (`SIM-01`, `SIM-VALID-API`, `SIM-FINAL`, `SIM-POSTEND`) |

El análisis principal sigue siendo `SIM-01`: **1.007 salidas, 374 superaciones
(37,14 %), 50 aviones**. `SIM-POSTEND` no se incluye en ese informe.

---

## 6. Limpieza opcional

Si no se quiere conservar la evidencia después de capturarla:

```javascript
const db = db.getSiblingDB("aeroflow");
db.vuelos.deleteMany({simulation_id: "SIM-POSTEND"});
db.operativos.deleteOne({simulation_id: "SIM-POSTEND"});
```

No es necesario para la entrega; la simulación está separada por `simulation_id` y
el informe filtra `SIM-01`.

---

## 7. Limitación conocida del generador

El generador evita que un mismo avión solape operaciones: la siguiente salida
programada se calcula como `salida_efectiva + 35 min`. Con retrasos de hasta 24 h,
muchas salidas programadas se empujan también más allá del fin del periodo. Por eso
solo **3** de las 101 salidas válidas cruzan exactamente el fin. Es suficiente para
la evidencia, pero no debe interpretarse como una distribución realista de retrasos:
`SIM-POSTEND` es un caso de prueba, no una simulación analítica.

---

## 8. Relación con las demás guías

- `GUIDE-nifi-flujo-vuelos.md`: validación, rechazo de defectos y colas del Funnel.
- `GUIDE-dremio-fuente-mongodb-vistas.md`: vistas D1–D9 y consulta de la evidencia
  en la sección 9.6.
- `README.md`: configuración del backend y catálogo fijo de destinos.
