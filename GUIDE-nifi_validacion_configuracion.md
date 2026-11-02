# Validación de la configuración en NiFi (`aeroflow.configuracion`)

Implementación del flujo que consume el topic de configuración, lo valida y lo
escribe en MongoDB (`aeroflow.operativos`) en **Apache NiFi 2.12.0**.

- **NiFi:** `https://nifi.monolith.dynamic-dns.net/nifi` (HTTPS 8443, usuario `hadoop`)
- **Kafka:** `localhost:9092` (PLAINTEXT), topic `aeroflow.configuracion`
- **MongoDB:** `localhost:27017`, base `aeroflow`, colección `operativos`
  (índice único en `simulation_id`)

> Esta guía sustituye la propuesta inicial: se ha implementado el flujo y se
> anotan las **alternativas** usadas porque algunas opciones del borrador **no
> existen o no funcionan** en la versión 2.12 de NiFi.

---

## 1. Flujo implementado

```
ConsumirConfiguracion ──success──▶ EnrutarConfiguracion ──configuration──▶ ValidarEsquema
   (ConsumeKafka)                    (RouteOnAttribute)                    (ValidateRecord)
                                                                            │      │
                                                              valid ────────┘      └──── invalid ──▶ Funnel (descartado)
                                                                 │
                                                        ExtraerCampos (EvaluateJsonPath)
                                                                 │ matched
                                                        ValidarRangos (RouteOnAttribute)
                                                             │            │
                                                   unmatched│            │invalid──▶ Funnel (descartado)
                                                             ▼
                                                  GuardarOperativos (PutMongoRecord, upsert)
```

| Procesador | Tipo | Función |
|---|---|---|
| `ConsumirConfiguracion` | `ConsumeKafka` | Lee el topic y expone las cabeceras |
| `EnrutarConfiguracion` | `RouteOnAttribute` | Filtra `message_type=configuration` |
| `ValidarEsquema` | `ValidateRecord` | Valida tipos y presencia (Avro **nivel 1 y anidados**) |
| `ExtraerCampos` | `EvaluateJsonPath` | Extrae valores anidados/arrays a atributos |
| `ValidarRangos` | `RouteOnAttribute` | Aplica reglas de rango con Expression Language |
| `GuardarOperativos` | `PutMongoRecord` | **Upsert** por `simulation_id` en `operativos` |

Controller services (root process group):

| Servicio | Tipo | Uso |
|---|---|---|
| `localhost:9092` | `Kafka3ConnectionService` | Conexión Kafka (solo `bootstrap.servers`, PLAINTEXT) |
| `MongoDBControllerService` | `MongoDBControllerService` | URI de Mongo con auth |
| `aeroflow-config-schema` | `AvroSchemaRegistry` | Esquema Avro de la configuración |
| `aeroflow-config-reader` | `JsonTreeReader` | Lee JSON validando contra el esquema |
| `aeroflow-config-writer` | `JsonRecordSetWriter` | Re-serializa a JSON |

---

## 2. Diferencia entre el mensaje de Kafka y el documento de Mongo

El productor publica `config.model_dump(mode="json")`, por lo que **las fechas
viajan como texto ISO 8601**:

- En Kafka: `"simulation_start": "2026-10-05T00:00:00Z"`
- En Mongo (tras el flujo): `2026-10-05T00:00:00.000Z` como **BSON Date**

La conversión a `Date` la hace `PutMongoRecord` automáticamente **si** el lector
declara el campo como `timestamp-millis` y tiene configurado el `Timestamp
Format`. Ver sección 6.

---

## 3. Controller services

### 3.1 AvroSchemaRegistry (`aeroflow-config-schema`)

Registro con una sola propiedad **dinámica** cuyo nombre es el del esquema
(`aeroflow.config`) y cuyo valor es el esquema Avro. Cubre los 15 campos de
primer nivel, incluidas las listas y el objeto anidado `generation_profiles`
(con sus mapas `map<double>`):

```json
{
  "type": "record", "name": "SimulationConfig", "namespace": "aeroflow",
  "fields": [
    {"name":"simulation_id","type":"string"},
    {"name":"name","type":"string"},
    {"name":"timezone","type":"string"},
    {"name":"simulation_start","type":{"type":"long","logicalType":"timestamp-millis"}},
    {"name":"simulation_days","type":"int"},
    {"name":"publish_interval_ms","type":"int"},
    {"name":"random_seed","type":"int"},
    {"name":"total_operations","type":"int"},
    {"name":"defect_rate","type":"double"},
    {"name":"destinations","type":{"type":"array","items":{"type":"record","name":"Destination",
        "fields":[{"name":"destination_id","type":"string"},{"name":"name","type":"string"}]}}},
    {"name":"gates","type":{"type":"array","items":{"type":"record","name":"Gate",
        "fields":[{"name":"gate_id","type":"string"},{"name":"name","type":"string"},
                  {"name":"terminal_id","type":"string"},{"name":"delay_threshold_minutes","type":"int"}]}}},
    {"name":"airlines","type":{"type":"array","items":{"type":"record","name":"Airline",
        "fields":[{"name":"airline","type":"string"},{"name":"flight_prefix","type":"string"}]}}},
    {"name":"aircraft_models","type":{"type":"array","items":{"type":"record","name":"AircraftModel",
        "fields":[{"name":"model_id","type":"string"},{"name":"name","type":"string"}]}}},
    {"name":"aircraft","type":{"type":"array","items":{"type":"record","name":"Aircraft",
        "fields":[{"name":"aircraft_id","type":"string"},{"name":"airline","type":"string"},
                  {"name":"aircraft_model","type":"string"}]}}},
    {"name":"generation_profiles","type":{"type":"record","name":"GenerationProfiles","fields":[
        {"name":"base_delay_probability","type":"double"},
        {"name":"gate_volume_weights","type":{"type":"map","values":"double"}},
        {"name":"destination_volume_weights","type":{"type":"map","values":"double"}},
        {"name":"time_band_volume_weights","type":{"type":"map","values":"double"}},
        {"name":"gate_delay_multipliers","type":{"type":"map","values":"double"}},
        {"name":"destination_delay_multipliers","type":{"type":"map","values":"double"}},
        {"name":"time_band_delay_multipliers","type":{"type":"map","values":"double"}},
        {"name":"max_delay_minutes_beyond_threshold","type":"int"}]}}
  ]
}
```

- **Validation Strategy:** `VALIDATE` (por defecto).

> **Alternativa aplicada:** el borrador decía que modelar los mapas de
> `generation_profiles` en Avro era "laborioso" y proponía validar solo el primer
> nivel. En la práctica **sí se modelan sin problema** con `type: map`,
> `values: double`; el `ValidateRecord` valida todo el árbol.

### 3.2 JsonTreeReader (`aeroflow-config-reader`)

| Propiedad | Valor |
|---|---|
| Schema Access Strategy | `schema-name` |
| Schema Registry | `aeroflow-config-schema` |
| Schema Name | `aeroflow.config` |
| Date Format | `yyyy-MM-dd'T'HH:mm:ssXXX` |
| Timestamp Format | `yyyy-MM-dd'T'HH:mm:ssXXX` |

> **⚠️ Alternativa clave (bug de versión):** con el formato del borrador
> (`yyyy-MM-dd'T'HH:mm:ss'Z'`, con `Z` entre comillas) la `Z` se interpreta como
> **literal**, y `2026-10-05T00:00:00Z` se guardaba como `2026-10-04T22:00:00Z`
> (**desfase de 2 h**). Usar el patrón **`XXX`** para el offset (que acepta `Z`
> como UTC). Con `XXX` la fecha se guarda exacta.

### 3.3 JsonRecordSetWriter (`aeroflow-config-writer`)

| Propiedad | Valor |
|---|---|
| Schema Write Strategy | `no-schema` |
| Schema Access Strategy | `inherit-record-schema` |
| Output Grouping | **`output-oneline`** |

> **⚠️ Alternativa clave:** por defecto `output-array` envuelve el registro en
> `[{...}]`, lo que rompe el paso siguiente (`EvaluateJsonPath` espera un objeto
> raíz). Con `output-oneline` se emite `{...}`.

---

## 4. Consumir y enrutar

### 4.1 `ConsumirConfiguracion` (ConsumeKafka)

| Propiedad | Valor |
|---|---|
| Kafka Connection Service | `localhost:9092` |
| Group ID | `config` |
| Topic Format | `names` |
| Topics | `aeroflow.configuracion` |
| auto.offset.reset | `latest` |
| Commit Offsets | `true` |
| **Header Name Pattern** | `[a-zA-Z0-9_.-]+` |
| **Header Name Prefix** | `kafka.header.` |

> **Alternativa clave:** el borrador asumía `${message.type}`. En NiFi 2.12 las
> cabeceras Kafka **no** se exponen por defecto; hay que activar
> **`Header Name Pattern`** (regex que selecciona las cabeceras) y
> **`Header Name Prefix`**. Así `message_type` queda como atributo
> **`kafka.header.message_type`** (verificado).

### 4.2 `EnrutarConfiguracion` (RouteOnAttribute)

Una propiedad (relación) `configuration`:

```
${kafka.header.message_type:equals('configuration'):or(${kafka.topic:equals('aeroflow.configuracion')})}
```

- **`unmatched`** → auto-terminado (o a un Funnel de descartados).

---

## 5. Validar el esquema (`ValidarEsquema`, ValidateRecord)

| Propiedad | Valor |
|---|---|
| Record Reader | `aeroflow-config-reader` |
| Record Writer | `aeroflow-config-writer` |
| Record Writer for Invalid Records | `aeroflow-config-writer` |
| Schema Access Strategy | `schema-name` |
| Schema Registry | `aeroflow-config-schema` |
| Schema Name | `aeroflow.config` |
| Allow Extra Fields | `true` |
| Strict Type Checking | `true` |
| Validation Details Attribute Name | `validation.details` |

Relaciones:
- **valid** → `ExtraerCampos`
- **invalid** → Funnel (descartado)
- **failure** → auto-terminado

> Tolerar propiedades adicionales (`Allow Extra Fields = true`) equivale a **no**
> aplicar `extra=forbid`. Los `invalid` traen el motivo en el atributo
> `validation.details` (útil para depurar).
>
> Nota: `LENGTH()` de campos array **no** es fiable combinarlo aquí; los
> conteos y rangos de arrays se hacen en el paso 6.

---

## 6. Validar rangos y anidados (la parte que el borrador resolvía con QueryRecord)

> **⚠️ Alternativa principal:** el borrador proponía `QueryRecord` con
> `SELECT ... WHERE gates[0].delay_threshold_minutes < 1`. **En esta versión
> Calcite no soporta acceso a campos anidados ni subíndices de array**: falla con
> `Table 'generation_profiles' not found` y manda el FlowFile a `failure`.
> `LENGTH(gates)` tampoco funciona. La alternativa que **sí funciona** es
> **`EvaluateJsonPath` + `RouteOnAttribute`**.

### 6.1 `ExtraerCampos` (EvaluateJsonPath)

Extrae a atributos de FlowFile los valores anidados/arrays con JSONPath:

| Atributo | JSONPath |
|---|---|
| `n_dest` | `$.destinations.length()` |
| `n_gates` | `$.gates.length()` |
| `n_airlines` | `$.airlines.length()` |
| `n_models` | `$.aircraft_models.length()` |
| `n_aircraft` | `$.aircraft.length()` |
| `g1`..`g5` | `$.gates[0..4].delay_threshold_minutes` |
| `base_delay` | `$.generation_profiles.base_delay_probability` |
| `max_delay` | `$.generation_profiles.max_delay_minutes_beyond_threshold` |
| `tz` | `$.timezone` |
| `sim_days` | `$.simulation_days` |
| `pub_int` | `$.publish_interval_ms` |
| `total_ops` | `$.total_operations` |
| `defect_rate` | `$.defect_rate` |

Configuración: `Destination=flowfile-attribute`, `Return Type=auto-detect`,
`Path Not Found Behavior=ignore`, `Null Value Representation=empty string`.
Relación **matched** → `ValidarRangos`; `failure`/`unmatched` auto-terminados.

> Verificado: `$.gates.length()` → `5`, `$.gates[0].delay_threshold_minutes` →
> `15`, `$.generation_profiles.base_delay_probability` → `0.24`.

### 6.2 `ValidarRangos` (RouteOnAttribute)

> **⚠️ Alternativa de sintaxis EL:** **no existen** las funciones `notEquals` ni
> `ne` (dan `Unexpected token`). Usar `equals(...):not()`. Y toda la condición
> debe ser **una única expresión** encadenada con `:or(...)`.

Una propiedad (relación) `invalid`:

```
${sim_days:lt(7):or(${sim_days:gt(31)})
:or(${pub_int:lt(0)}):or(${pub_int:gt(60000)})
:or(${total_ops:lt(100)}):or(${total_ops:gt(100000)})
:or(${defect_rate:lt(0.05)}):or(${defect_rate:gt(0.05)})
:or(${tz:equals('Europe/Madrid'):not()})
:or(${n_gates:lt(5)}):or(${n_gates:gt(5)})
:or(${n_dest:lt(1)}):or(${n_airlines:lt(1)}):or(${n_models:lt(1)}):or(${n_aircraft:lt(1)})
:or(${g1:lt(1)}):or(${g2:lt(1)}):or(${g3:lt(1)}):or(${g4:lt(1)}):or(${g5:lt(1)})
:or(${base_delay:lt(0)}):or(${base_delay:gt(1)})
:or(${max_delay:lt(1)}):or(${max_delay:gt(1440)})}
```

Reglas cubiertas:
- `simulation_days` ∈ `[7,31]`
- `publish_interval_ms` ∈ `[0,60000]`
- `total_operations` ∈ `[100,100000]`
- `defect_rate` = `0.05`
- `timezone` = `Europe/Madrid`
- `gates` exactamente 5, `delay_threshold_minutes > 0`
- `destinations`/`airlines`/`aircraft_models`/`aircraft` ≥ 1
- `base_delay_probability` ∈ `[0,1]`
- `max_delay_minutes_beyond_threshold` ∈ `[1,1440]`

Relaciones:
- **invalid** → Funnel (descartado)
- **unmatched** → `GuardarOperativos`

---

## 7. Insertar con upsert (`GuardarOperativos`, PutMongoRecord)

| Propiedad | Valor |
|---|---|
| Client Service | `MongoDBControllerService` |
| Mongo Database Name | `aeroflow` |
| Mongo Collection Name | **`operativos`** |
| Record Reader | `aeroflow-config-reader` |
| **Update Key Fields** | **`simulation_id`** |
| Update Mode | `one` |

Relaciones: `success` y `failure` auto-terminados.

> **Clave:** `PutMongoRecord` hace **upsert** cuando se rellena
> `Update Key Fields` (si se deja vacío, hace `insert`). Con `simulation_id`
> como clave se respeta el índice único y **no se duplica** el documento que el
> backend ya escribió.
>
> **No hace falta** un `UpdateRecord` previo para convertir la fecha: al leer
> `simulation_start` como `timestamp-millis` (sección 3.2) y re-leerlo en
> `PutMongoRecord` con el mismo reader, se escribe como **BSON Date**.

---

## 8. Función de descarte (Funnel)

Todos los `invalid`/`unmatched`/`failure` se enrutan a un **Funnel**
(`Funnel descartados`). Nada inválido llega a MongoDB.

---

## 9. Verificación realizada

| Caso | Entrada | Resultado |
|---|---|---|
| Válido | `SIM-VALID-API` (mensaje completo) | insertado en `operativos`; `simulation_start` = **Date** `2026-10-05T00:00:00.000Z` |
| Reenvío mismo id | `SIM-VALID-API` otra vez | **upsert**: el conteo no cambia (no duplica) |
| Tipo inválido | `simulation_days: "x"` | `ValidarEsquema → invalid` (reason: `/simulation_days`), **no** insertado |
| Rango inválido | `simulation_days: 3` | `ValidarRangos → invalid`, **no** insertado |

Comprobación en Mongo:

```bash
mongosh "mongodb://admin:<PASS>@localhost:27017/?authSource=admin" --quiet --eval '
  print("operativos:", db.getSiblingDB("aeroflow").operativos.countDocuments());
  print(JSON.stringify(db.getSiblingDB("aeroflow").operativos.distinct("simulation_id")));
  var d = db.getSiblingDB("aeroflow").operativos.findOne({simulation_id:"SIM-VALID-API"});
  print(d.simulation_start.constructor.name, d.simulation_start.toISOString());'
```

---

## 10. Resumen de alternativas respecto al borrador original

| Punto del borrador | Problema en NiFi 2.12 | Alternativa implementada |
|---|---|---|
| `${message.type}` para rutar | Las cabeceras no se exponen por defecto | `Header Name Pattern` + prefijo → `kafka.header.message_type` |
| Modelar `generation_profiles` en Avro es "laborioso" | Se puede hacer bien | `type: map` / `values: double` en el esquema |
| `ConvertRecord`/`QueryRecord` para rangos | Calcite no soporta anidados ni `array[i]`; `LENGTH(array)` falla | `EvaluateJsonPath` + `RouteOnAttribute` |
| `WHERE ... gates[0]...` | `Table 'generation_profiles' not found` | JSONPath `$.gates[0]...` en `EvaluateJsonPath` |
| `notEquals` en EL | No existe | `equals(...):not()` |
| Fecha como string ISO | Desfase de 2 h con `'Z'` literal | `Timestamp Format = yyyy-MM-dd'T'HH:mm:ssXXX` |
| Salida del validador en array | `[{...}]` rompe el JSONPath | `JsonRecordSetWriter → output-oneline` |
| Upsert por `simulation_id` | `insert` duplica / rompe índice único | `PutMongoRecord` con `Update Key Fields = simulation_id` |

### Aspectos que se mantienen del borrador

- La colección es `operativos` (no `configuracion`) con índice único en
  `simulation_id`.
- `record_valid` es exclusivo de los vuelos, no de la configuración.
- No se reimplementan en NiFi todas las validaciones cruzadas del backend
  (equilibrio de flota, unicidad de prefijos, mínimos por compañía): la autoridad
  es el backend. El flujo valida tipos, presencia y rangos.
- Tolerar propiedades adicionales (no `extra=forbid`).

---

## 11. Notas

- **Reinicio de processors tras tocar controller services:** deshabilitar un
  controller service (p. ej. el reader/writer) detiene los processors que lo
  usan. Hay que volver a arrancarlos.
- **`ResultSet` sin nombre de esquema:** `QueryRecord` (si se usa) pierde el
  nombre de esquema al heredar del resultado; por eso el writer usa
  `no-schema` (no intenta escribir el nombre). Relevante solo si
  reintroduces `QueryRecord` para campos de primer nivel.
- **Duplicados:** el upsert evita duplicados solo si `simulation_id` está
  presente; `ValidarEsquema` garantiza que no falte.
- Documento relacionado: `GUIDE-nifi-flujo-kafka-mongodb.md` (variante simple
  Consume→PutMongo) y `GUIDE-traefik-servicios-nativos-192.168.0.26.md`.
