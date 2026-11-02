# Guía: flujo NiFi de ingesta de vuelos (`aeroflow.vuelos` → `vuelos`)

Guía paso a paso de la construcción, **mediante la API REST de Apache NiFi 2.12.0**,
del flujo que consume las salidas del simulador, valida el contrato, separa los
registros inválidos y hace *upsert* en MongoDB.

- **NiFi:** `https://nifi.monolith.dynamic-dns.net/nifi` (nativo en `192.168.0.26`, HTTPS 8443)
- **Kafka:** `localhost:9092` (PLAINTEXT, listener INTERNAL de la propia máquina)
- **MongoDB:** `localhost:27017` (auth `admin`), base `aeroflow`, colección `vuelos`
- **Credenciales NiFi:** usuario `hadoop`, contraseña `hadoophadoop`
- **Root process group:** `d30416dd-01a0-1000-8f80-d3893eb9e452`

> Flujo construido el 2026-11-02. Sustituye la práctica `aeroflow.vuelos_consumidor_kafka`
> (ConsumeKafka → PutFile), que se dejó **parada** y no forma parte de la ingesta.

---

## 1. Comprobación previa de la máquina

```bash
for s in kafka nifi mongod dremio; do
  printf "%-7s %-8s %-8s\n" "$s" "$(systemctl is-enabled $s)" "$(systemctl is-active $s)"
done
```

Resultado esperado: los cuatro servicios `enabled / active`.

```bash
ss -ltnp | grep -E ':(9092|9095|8443|27017|9047)\b'
```

| Puerto | Servicio |
|---|---|
| `9092` | Kafka INTERNAL (PLAINTEXT, para NiFi/Dremio) |
| `9095` | Kafka EXTERNAL (Traefik) |
| `8443` | NiFi HTTPS |
| `27017` | MongoDB |
| `9047` | Dremio |

MongoDB debe tener los índices de `vuelos` (los crea el backend al arrancar):

```bash
mongosh "mongodb://admin:<PASS>@localhost:27017/?authSource=admin" --quiet --eval '
  const d=db.getSiblingDB("aeroflow");
  print("docs vuelos:", d.vuelos.countDocuments());
  printjson(d.vuelos.getIndexes().map(i=>i.name));'
```

> **Índice clave:** `event_id_1` es **único**; el *upsert* del flujo y el índice
> convierten un reenvío en una actualización, no en un documento nuevo.

---

## 2. Autenticación en la API de NiFi

La API **solo emite tokens por HTTPS**. Además, NiFi valida el **SNI**: si se
llama a `https://localhost:8443` responde `400 Invalid SNI`. Hay que usar el
nombre del certificado (`nifi.monolith.dynamic-dns.net`).

### Desde fuera de la VM (por Traefik, puerto 443)

```bash
TOKEN=$(curl -sk -X POST https://nifi.monolith.dynamic-dns.net/nifi-api/access/token \
  -d 'username=hadoop&password=hadoophadoop')
```

### Desde la propia VM

```bash
H=nifi.monolith.dynamic-dns.net
TOKEN=$(curl -sk --resolve $H:8443:127.0.0.1 -X POST \
  https://$H:8443/nifi-api/access/token -d 'username=hadoop&password=hadoophadoop')
```

Todas las llamadas siguientes llevan:

```bash
-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"
```

Variables usadas en los ejemplos:

```bash
ROOT=d30416dd-01a0-1000-8f80-d3893eb9e452
BASE=https://nifi.monolith.dynamic-dns.net/nifi-api
```

---

## 3. Estructura del flujo

```text
ConsumirVuelos ──success──▶ EnrutarVuelos ──flight──▶ ValidarEsquemaVuelo ──valid──▶ ClasificarVuelo
   (ConsumeKafka)            (RouteOnAttribute)          (ValidateRecord)              (QueryRecord)
                                   │                            │                            │
                                   ├─ prueba ──────────┐        ├─ invalid ──────────┐      ├─ validos ──▶ GuardarVuelo
                                   └─ unmatched ───────┤        └─ failure ──────────┤      └─ invalidos ─┐   (PutMongoRecord)
                                                       ▼                             ▼                    ▼
                                                   DescartesVuelos (Funnel) ◀─────────┴────────────────────┘
                                                                                    (failure del PutMongo)
```

| Procesador | Tipo | Función |
|---|---|---|
| `ConsumirVuelos` | `ConsumeKafka` | Lee `aeroflow.vuelos` y expone las cabeceras |
| `EnrutarVuelos` | `RouteOnAttribute` | Separa vuelos (`flight`), pruebas (`test`) y sin cabecera |
| `ValidarEsquemaVuelo` | `ValidateRecord` | Valida tipos y presencia con esquema Avro |
| `ClasificarVuelo` | `QueryRecord` | Reglas de negocio y formato de identificadores |
| `GuardarVuelo` | `PutMongoRecord` | *Upsert* por `event_id` en `aeroflow.vuelos` |
| `DescartesVuelos` | `Funnel` | Cola de inspección manual de rechazados |

---

## 4. Controller services

Se crean en el **root process group** y se habilitan antes de usarlos.
La API de creación exige `revision.version = 0`.

### 4.1 Esquema Avro (`aeroflow-flight-schema`)

```bash
curl -sk -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -X POST https://nifi.monolith.dynamic-dns.net/nifi-api/process-groups/$ROOT/controller-services \
  -d '{"revision":{"version":0},
       "component":{"type":"org.apache.nifi.schemaregistry.services.AvroSchemaRegistry",
                    "name":"aeroflow-flight-schema"}}'
```

Se añade una propiedad dinámica `aeroflow.flight` con el esquema:

```json
{
  "type": "record", "name": "FlightEvent", "namespace": "aeroflow",
  "fields": [
    {"name":"event_id","type":"string"},
    {"name":"schema_version","type":"int"},
    {"name":"simulation_id","type":"string"},
    {"name":"scheduled_departure_at","type":{"type":"long","logicalType":"timestamp-millis"}},
    {"name":"actual_departure_at","type":{"type":"long","logicalType":"timestamp-millis"}},
    {"name":"emitted_at","type":{"type":"long","logicalType":"timestamp-millis"}},
    {"name":"terminal_id","type":"string"},
    {"name":"gate_id","type":"string"},
    {"name":"aircraft_id","type":"string"},
    {"name":"operation_id","type":"string"},
    {"name":"flight_number","type":"string"},
    {"name":"airline","type":"string"},
    {"name":"aircraft_model","type":"string"},
    {"name":"destination_id","type":"string"},
    {"name":"delay_threshold_minutes","type":"int"},
    {"name":"record_valid","type":"boolean"}
  ]
}
```

> **Obligatorios:** todos los campos. Un mensaje con un campo ausente va a
> `invalid`; un JSON malformado va a `failure`. Ambos terminan en el Funnel.

### 4.2 Lector JSON (`aeroflow-flight-reader`)

`JsonTreeReader` con:

| Propiedad | Valor |
|---|---|
| Schema Access Strategy | `schema-name` |
| Schema Registry | `aeroflow-flight-schema` |
| Schema Name | `aeroflow.flight` |
| Date Format | `yyyy-MM-dd'T'HH:mm:ss[.SSSSSS]XXX` |
| Timestamp Format | `yyyy-MM-dd'T'HH:mm:ss[.SSSSSS]XXX` |

> **⚠️ Clave:** `emitted_at` lo genera el backend con `datetime.now(timezone.utc)`,
> que incluye **microsegundos** (`2026-11-02T16:33:20.205882Z`). Con el formato
> `...ssXXX` todos los vuelos reales se rechazaban. La sección opcional
> `[.SSSSSS]` acepta fechas con y sin fracción.

### 4.3 Escritor JSON (`aeroflow-flight-writer`)

`JsonRecordSetWriter` con:

| Propiedad | Valor |
|---|---|
| Schema Write Strategy | `no-schema` |
| Schema Access Strategy | `inherit-record-schema` |
| Pretty Print JSON | `false` |
| Output Grouping | `output-oneline` |

> `output-oneline` evita que el resultado salga como `[{...}]`; `no-schema` evita
> intentar escribir el nombre del esquema del `ResultSet` de `QueryRecord`.

### 4.4 Actualizar y habilitar por API

Un servicio **ENABLED no se puede modificar**: primero se deshabilita.

```bash
# Deshabilitar (revision actual)
curl -sk -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://nifi.monolith.dynamic-dns.net/nifi-api/controller-services/$ID/run-status \
  -d '{"revision":{"version":N},"state":"DISABLED"}'

# PUT con las propiedades (misma revisión devuelta)
curl -sk -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://nifi.monolith.dynamic-dns.net/nifi-api/controller-services/$ID \
  -d '{"revision":{"version":N},"component":{"id":"'$ID'","type":"...","name":"...","properties":{...}}}'

# Habilitar
curl -sk -X PUT .../controller-services/$ID/run-status \
  -d '{"revision":{"version":M},"state":"ENABLED"}'
```

---

## 5. Procesadores

Creación (una vez por procesador):

```bash
curl -sk -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://nifi.monolith.dynamic-dns.net/nifi-api/process-groups/$ROOT/processors \
  -d '{"revision":{"version":0},
       "component":{"type":"<tipo>","name":"<nombre>","position":{"x":X,"y":Y}}}'
```

La actualización se hace con `PUT /processors/{id}` enviando
`component.config.properties` y `component.config.autoTerminatedRelationships`.

### 5.1 `ConsumirVuelos` — ConsumeKafka

| Propiedad | Valor |
|---|---|
| Kafka Connection Service | `localhost:9092` |
| Group ID | `aeroflow-vuelos` |
| Topic Format | `names` |
| Topics | `aeroflow.vuelos` |
| auto.offset.reset | `earliest` |
| Commit Offsets | `true` |
| Header Name Pattern | `[a-zA-Z0-9_.-]+` |
| Header Name Prefix | `kafka.header.` |

> En NiFi 2.12 las cabeceras Kafka **no** se exponen por defecto. Con el patrón y
> el prefijo, `message_type` queda como `${kafka.header.message_type}`.
> Relación `success` → `EnrutarVuelos`. Sin auto-terminar.

### 5.2 `EnrutarVuelos` — RouteOnAttribute

| Propiedad (relación) | Expresión |
|---|---|
| `flight` | `${kafka.header.message_type:equals('flight')}` |
| `prueba` | `${kafka.header.message_type:equals('test')}` |

- `flight` → `ValidarEsquemaVuelo`
- `prueba` → `DescartesVuelos` (los casos de `/test-events` son ilegibles a propósito)
- `unmatched` → `DescartesVuelos`

### 5.3 `ValidarEsquemaVuelo` — ValidateRecord

| Propiedad | Valor |
|---|---|
| Record Reader | `aeroflow-flight-reader` |
| Record Writer | `aeroflow-flight-writer` |
| Record Writer for Invalid Records | `aeroflow-flight-writer` |
| Schema Access Strategy | `schema-name` |
| Schema Registry | `aeroflow-flight-schema` |
| Schema Name | `aeroflow.flight` |
| Allow Extra Fields | `true` |
| Strict Type Checking | `true` |
| Validation Details Attribute Name | `validation.details` |

- `valid` → `ClasificarVuelo`
- `invalid` → Funnel
- `failure` → Funnel

### 5.4 `ClasificarVuelo` — QueryRecord

| Propiedad | Valor |
|---|---|
| Record Reader | `aeroflow-flight-reader` |
| Record Writer | `aeroflow-flight-writer` |
| Include Zero Record FlowFiles | `false` |
| Auto-terminated | `original` |

Propiedades **dinámicas** (el nombre de la propiedad es la relación de salida):

`validos`:

```sql
SELECT * FROM FLOWFILE
WHERE record_valid = TRUE
  AND schema_version = 1
  AND actual_departure_at >= scheduled_departure_at
  AND delay_threshold_minutes > 0
  AND event_id LIKE 'EV-%'
  AND simulation_id LIKE 'SIM-%'
  AND operation_id LIKE 'OP-%'
  AND aircraft_id LIKE 'AV-%'
  AND gate_id IN ('G1','G2','G3','G4','G5')
  AND terminal_id IN ('T1','T2','T3','T4','T5')
  AND destination_id LIKE 'DEST-%'
  AND destination_id IN ('DEST-01','DEST-02','DEST-03','DEST-04')
```

`invalidos` (complemento exacto):

```sql
SELECT * FROM FLOWFILE
WHERE record_valid = FALSE
   OR schema_version <> 1
   OR actual_departure_at < scheduled_departure_at
   OR delay_threshold_minutes <= 0
   OR event_id NOT LIKE 'EV-%'
   OR simulation_id NOT LIKE 'SIM-%'
   OR operation_id NOT LIKE 'OP-%'
   OR aircraft_id NOT LIKE 'AV-%'
   OR gate_id NOT IN ('G1','G2','G3','G4','G5')
   OR terminal_id NOT IN ('T1','T2','T3','T4','T5')
   OR destination_id NOT LIKE 'DEST-%'
   OR destination_id NOT IN ('DEST-01','DEST-02','DEST-03','DEST-04')
```

> **Lista de destinos permitidos.** La regla `IN (...)` se añadió para que un
> `destination_id` con formato válido pero fuera del catálogo (`DEST-UNKNOWN`,
> `DEST-99`, etc.) también acabe en el Funnel. La lista se corresponde con el
> catálogo fijo del escenario. El modelo del backend y la API rechazan cualquier
> configuración con otro catálogo, y el formulario web mostrará los destinos en
> modo lectura. Así la lista de NiFi y la del backend no pueden desincronizarse.
> Una alternativa más general sería un `LookupRecord` contra `operativos`; no es
> necesaria mientras el catálogo sea fijo.

- `validos` → `GuardarVuelo`
- `invalidos` → Funnel
- `failure` → Funnel
- `original` → auto-terminado (el FlowFile original no se necesita)

> **Por qué funciona el filtrado:** `QueryRecord` crea una **relación dinámica
> por cada propiedad SQL**, y `original` recibe el FlowFile de entrada. Con
> `Include Zero Record FlowFiles = false`, si una consulta no selecciona filas no
> se emite FlowFile. Al ser `validos` e `invalidos` complementarios, cada vuelo
> sale exactamente por una rama.
>
> Se usa `LIKE`/`IN` (soportados por Calcite) para el formato de identificadores.
> No se accede a campos anidados ni arrays, que es lo que falla en esta versión.

### 5.5 `GuardarVuelo` — PutMongoRecord

| Propiedad | Valor |
|---|---|
| Client Service | `MongoDBControllerService` |
| Mongo Database Name | `aeroflow` |
| Mongo Collection Name | `vuelos` |
| Record Reader | `aeroflow-flight-reader` |
| Update Key Fields | `event_id` |
| Update Mode | `one` |
| Batch Size | `100` |
| Ordered | `False` |
| Bypass Validation | `False` |

- `success` → auto-terminado
- `failure` → Funnel

> `Update Key Fields = event_id` activa el **upsert**. Sin él, `PutMongoRecord`
> insertaría y el índice único `event_id_1` provocaría errores en los reenvíos.

### 5.6 `DescartesVuelos` — Funnel

Los Funnel **no tienen nombre** en NiFi. Se crean con:

```bash
curl -sk -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://nifi.monolith.dynamic-dns.net/nifi-api/process-groups/$ROOT/funnels \
  -d '{"revision":{"version":0},"component":{"name":"DescartesVuelos","position":{"x":300,"y":900}}}'
```

La API los devuelve solo con `id` y `position`; para localizarlos hay que usar la
posición.

---

## 6. Conexiones

```bash
curl -sk -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://nifi.monolith.dynamic-dns.net/nifi-api/process-groups/$ROOT/connections \
  -d '{"revision":{"version":0},
       "component":{
         "source":{"id":"<origen>","groupId":"'$ROOT'","type":"PROCESSOR"},
         "destination":{"id":"<destino>","groupId":"'$ROOT'","type":"PROCESSOR"},
         "selectedRelationships":["success"],
         "backPressureDataSizeThreshold":"1 GB",
         "backPressureObjectThreshold":10000,
         "flowFileExpiration":"0 sec"}}'
```

| Origen | Relación | Destino |
|---|---|---|
| `ConsumirVuelos` | `success` | `EnrutarVuelos` |
| `EnrutarVuelos` | `flight` | `ValidarEsquemaVuelo` |
| `EnrutarVuelos` | `prueba` | `DescartesVuelos` (FUNNEL) |
| `EnrutarVuelos` | `unmatched` | `DescartesVuelos` (FUNNEL) |
| `ValidarEsquemaVuelo` | `valid` | `ClasificarVuelo` |
| `ValidarEsquemaVuelo` | `invalid` | `DescartesVuelos` (FUNNEL) |
| `ValidarEsquemaVuelo` | `failure` | `DescartesVuelos` (FUNNEL) |
| `ClasificarVuelo` | `validos` | `GuardarVuelo` |
| `ClasificarVuelo` | `invalidos` | `DescartesVuelos` (FUNNEL) |
| `ClasificarVuelo` | `failure` | `DescartesVuelos` (FUNNEL) |
| `GuardarVuelo` | `failure` | `DescartesVuelos` (FUNNEL) |

---

## 7. Arranque

Se arranca **de destino a origen** para que no se acumulen colas:

```bash
for ID in $GUARDAR $CLASIFICAR $VALIDAR $ENRUTAR $CONSUMIR; do
  REV=$(curl -sk -H "Authorization: Bearer $TOKEN" .../processors/$ID | jq -r .revision.version)
  curl -sk -X PUT .../processors/$ID/run-status \
    -d '{"revision":{"version":'$REV'},"state":"RUNNING"}'
done
```

Estado final esperado: los cinco procesadores en `RUNNING`, sin
`validationErrors` y con las relaciones no usadas auto-terminadas.

---

## 8. Verificación end-to-end

### 8.1 Casos de prueba

Se publicaron con un productor `confluent_kafka` sobre `aeroflow.vuelos`:

| Caso | Cabecera | Resultado observado |
|---|---|---|
| Vuelo válido (`EV-TESTNIFI-0001`) | `flight` | Insertado en `vuelos` |
| Mismo evento reenviado | `flight` | **No** duplica (upsert por `event_id`) |
| `record_valid=false` (completo) | `flight` | `invalidos` → Funnel |
| `schema_version=2` | `flight` | `invalidos` → Funnel |
| `actual_departure_at < scheduled` | `flight` | `invalidos` → Funnel |
| `delay_threshold_minutes=0` | `flight` | `invalidos` → Funnel |
| `event_id="BADID"` | `flight` | `invalidos` → Funnel |
| `gate_id="G9"` | `flight` | `invalidos` → Funnel |
| `terminal_id="T9"` | `flight` | `invalidos` → Funnel |
| `destination_id="DEST-UNKNOWN"` (13 casos de la simulación) | `flight` | `invalidos` → Funnel |
| JSON malformado | `flight` | `failure` → Funnel |
| Campos ausentes | `flight` | `invalid` → Funnel |
| Caso de `/test-events` | `test` | `prueba` → Funnel |

Comprobación en MongoDB:

```bash
mongosh "mongodb://admin:<PASS>@localhost:27017/?authSource=admin" --quiet --eval '
  const v=db.getSiblingDB("aeroflow").vuelos;
  print("total:", v.countDocuments());
  print("event_id únicos:", v.distinct("event_id").length);
  printjson(v.findOne({event_id:"EV-TESTNIFI-0001"}));'
```

### 8.2 Inspección de la cola de descartes

El Funnel no se puede abrir como una colección, pero la **conexión que llega a
él** sí tiene cola inspeccionable:

```bash
# 1. pedir listado de la cola
curl -sk -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://nifi.monolith.dynamic-dns.net/nifi-api/flowfile-queues/$CONN_ID/listing-requests \
  -d '{"drop":false}'

# 2. consultar el listado con el id devuelto
curl -sk -H "Authorization: Bearer $TOKEN" \
  .../flowfile-queues/$CONN_ID/listing-requests/$REQUEST_ID
```

En la UI: clic derecho sobre la conexión → **List Queue**, o sobre el procesador
→ **View Data Provenance** (el atributo `validation.details` indica el motivo).

### 8.3 Simulación completa

Con el backend en marcha:

```bash
curl -X POST http://127.0.0.1:8000/api/simulations/SIM-01/start
curl http://127.0.0.1:8000/api/simulations/status
```

Resultado de la ejecución de referencia:

| Métrica | Valor |
|---|---|
| Eventos publicados por el simulador | **1060** |
| Documentos `SIM-01` en `vuelos` | **1007** |
| `event_id` únicos en `SIM-01` | **1007** (0 duplicados) |
| Rechazados por NiFi | **53** (5,0 %: los 53 defectos del generador) |
| Documentos totales en `vuelos` (estado actual) | **1.109** (1.007 de `SIM-01` + 1 de prueba + 101 de `SIM-POSTEND`) |

Distribución por puerta:

```text
G1: 257   G2: 183   G3: 224   G4: 206   G5: 137
```

Los 53 rechazos se reparten así: **14** en `ValidarEsquemaVuelo` (campos ausentes o
tipos inválidos) y **39** en `ClasificarVuelo` (13 umbrales no positivos, 13 salidas
efectivas anteriores a la programada y 13 destinos fuera del catálogo). Comprobación:

```javascript
const v = db.getSiblingDB("aeroflow").vuelos;
print("SIM-01:", v.countDocuments({simulation_id: "SIM-01"}));
print("DEST-UNKNOWN:", v.countDocuments({simulation_id: "SIM-01", destination_id: "DEST-UNKNOWN"}));
print("duplicados:", v.aggregate([
  {$match: {simulation_id: "SIM-01"}},
  {$group: {_id: "$event_id", n: {$sum: 1}}},
  {$match: {n: {$gt: 1}}}
]).toArray().length);
```

Resultado esperado: `SIM-01: 1007`, `DEST-UNKNOWN: 0`, `duplicados: 0`.

> **Evidencia post-fin.** `SIM-POSTEND` añade 101 salidas válidas y 3 cruces del fin
> del periodo (`EV-SIM-POSTEND-000033`, `-000078` y `-000100`). Se documenta en
> `GUIDE-simulacion-postend.md`; no altera el análisis de `SIM-01`.

Documento de ejemplo (fechas ya como BSON `Date`):

```json
{
  "event_id": "EV-SIM-01-000594",
  "gate_id": "G2",
  "terminal_id": "T2",
  "scheduled_departure_at": "2026-10-11T21:48:00.000Z",
  "actual_departure_at": "2026-10-11T22:03:00.000Z",
  "emitted_at": "2026-11-02T17:38:49.180Z",
  "record_valid": true
}
```

> El 5 % de operaciones defectuosas del generador (53 de 1060) se rechaza completo:
> campo ausente, umbral no positivo, salida efectiva anterior, JSON/esquema inválido
> y destino fuera del catálogo (`DEST-UNKNOWN`). Ningún registro defectuoso llega a
> `vuelos`. La regla de destino permitido se añadió a `ClasificarVuelo` y se validó
> con los 13 casos `DEST-UNKNOWN` de la simulación.

---

## 9. Incidencias y decisiones

| Punto | Problema | Solución aplicada |
|---|---|---|
| SNI | `https://localhost:8443` → `400 Invalid SNI` | Usar el hostname del certificado o `--resolve` |
| Creación por API | `A revision of 0 must be specified` | Enviar `"revision":{"version":0}` |
| Modificar un servicio | `not disabled - state ENABLED` | `DISABLED` → `PUT` → `ENABLED` |
| Funnels | No tienen nombre | Identificarlos por `position` |
| Cabeceras Kafka | No llegan como atributos | `Header Name Pattern` + `Header Name Prefix` |
| Fechas con microsegundos | Todos los vuelos reales a `invalid` | `yyyy-MM-dd'T'HH:mm:ss[.SSSSSS]XXX` |
| Salida de `QueryRecord` | `original` recibía el FlowFile de entrada | Auto-terminar `original` |
| Consultas sin filas | Emitían FlowFiles vacíos | `Include Zero Record FlowFiles = false` |
| Duplicados | `insert` duplicaría | `PutMongoRecord` con `Update Key Fields = event_id` |
| Calcite | No soporta campos anidados/arrays | Las reglas usan solo campos de primer nivel |
| Destino fuera de catálogo | `DEST-UNKNOWN` pasaba como formato válido | Añadir `destination_id IN (catálogo)` a `validos` e `invalidos` |

### IDs de esta instalación

| Elemento | ID |
|---|---|
| Root process group | `d30416dd-01a0-1000-8f80-d3893eb9e452` |
| `aeroflow-flight-schema` | `9d1990b6-01a1-1000-8176-cf8bed8c9467` |
| `aeroflow-flight-reader` | `9d1992e4-01a1-1000-6962-58b26b59fad7` |
| `aeroflow-flight-writer` | `9d1994a0-01a1-1000-4687-649e57761db6` |
| `ConsumirVuelos` | `9d19e5a9-01a1-1000-ecbe-8a552c40c7b3` |
| `EnrutarVuelos` | `9d19e761-01a1-1000-5539-cc0d46698c03` |
| `ValidarEsquemaVuelo` | `9d19e907-01a1-1000-bdf5-39d372df0c10` |
| `ClasificarVuelo` | `9d19eab5-01a1-1000-749e-90ea6d010d27` |
| `GuardarVuelo` | `9d19ed4a-01a1-1000-f4ec-1e312e5f4083` |
| `DescartesVuelos` | `9d19e4f6-01a1-1000-4f13-12156ff348c4` |

---

## 10. Estado final

```text
ConsumirVuelos        | RUNNING | errors: 0
EnrutarVuelos         | RUNNING | errors: 0
ValidarEsquemaVuelo   | RUNNING | errors: 0
ClasificarVuelo       | RUNNING | errors: 0
GuardarVuelo          | RUNNING | errors: 0
aeroflow-flight-schema / reader / writer: ENABLED
Consumer group aeroflow-vuelos: LAG 0
```

Con esto, la cadena **simulador → Kafka → NiFi → MongoDB** queda completa para
las salidas. Dremio ya tiene las vistas D1–D9 sobre esta colección; los siguientes
pasos son la web y Power BI.

---

## 11. Notas

- La práctica antigua `aeroflow.vuelos_consumidor_kafka` (ConsumeKafka → MergeContent
  → PutFile) sigue **STOPPED**; no interfiere con este flujo.
- El flujo de configuración (`ConsumirConfiguracion`) y el de vuelos comparten los
  controller services de Kafka y MongoDB, pero usan **consumer groups distintos**
  (`config` y `aeroflow-vuelos`).
- Si hay que reprocesar desde el principio:
  1. Parar `ConsumirVuelos`.
  2. `kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group aeroflow-vuelos --topic aeroflow.vuelos --reset-offsets --to-earliest --execute`
  3. Vaciar `vuelos` de esa simulación (`deleteMany`) o confiar en el upsert por `event_id`.
  4. Volver a arrancar. Los `event_id` ya insertados se actualizan, no se duplican.
- **Destinos permitidos:** el catálogo es fijo (`DEST-01`…`DEST-04`). El modelo
  Pydantic y `POST /api/configurations` rechazan cualquier otro catálogo, y el
  formulario web muestra los destinos en modo lectura. Así `ClasificarVuelo` y el
  backend validan exactamente la misma lista. Si en el futuro se quisiera un
  catálogo variable, habría que sustituir la lista por un `LookupRecord` contra
  `operativos`.
- Documentos relacionados: `GUIDE-nifi-flujo-kafka-mongodb.md`,
  `GUIDE-nifi_validacion_configuracion.md`,
  `GUIDE-simulacion-postend.md` y
  `GUIDE-traefik-servicios-nativos-192.168.0.26.md`.
