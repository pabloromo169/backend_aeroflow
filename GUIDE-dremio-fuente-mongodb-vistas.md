# Guía: fuente MongoDB y vistas D1–D9 en Dremio (AeroFlow)

Guía paso a paso de la integración de **Dremio 26.0.5** con **MongoDB 8.2.12** y de la
construcción de las **nueve vistas analíticas** del proyecto AeroFlow.

- **Dremio:** `http://192.168.0.26:9047` (nativo en la VM) y `https://dremio.monolith.dynamic-dns.net` (Traefik)
- **MongoDB:** `localhost:27017`, autenticación `admin`, base `aeroflow`
- **Fuente Dremio:** `mongo_aeroflow` (tipo `MONGO`)
- **Espacio Dremio:** `Aeroflow`
- **Fecha de construcción:** 2026-11-02
- **Datos analizados:** simulación `SIM-01` (1.007 salidas válidas, 50 aviones distintos)
- **Evidencia post-fin:** simulación `SIM-POSTEND` (101 salidas válidas, 3 cruces del fin)

> **Credenciales.** En esta guía se usan los marcadores `<DREMIO_PASSWORD>` y
> `<MONGO_ADMIN_PASSWORD>`. Las credenciales reales no se escriben en el repositorio:
> la contraseña de MongoDB está en `/root/.mongo_admin_pw` de la VM y la de Dremio
> fue proporcionada para el aula. No se debe versionar ningún secreto.

---

## Índice

1. [Objetivo y resultado](#1-objetivo-y-resultado)
2. [Comprobaciones previas](#2-comprobaciones-previas)
3. [Acceso a Dremio y autenticación en la API](#3-acceso-a-dremio-y-autenticación-en-la-api)
4. [Creación de la fuente MongoDB](#4-creación-de-la-fuente-mongodb)
5. [Exploración del catálogo y tipos de datos](#5-exploración-del-catálogo-y-tipos-de-datos)
6. [Decisiones de SQL y dialecto de Dremio](#6-decisiones-de-sql-y-dialecto-de-dremio)
7. [Espacio `Aeroflow` y vistas base](#7-espacio-aeroflow-y-vistas-base)
8. [Vistas D1–D9](#8-vistas-d1d9)
9. [Reconciliación y pruebas de validación](#9-reconciliación-y-pruebas-de-validación)
10. [Gestión de vistas por API](#10-gestión-de-vistas-por-api)
11. [Conexión desde Power BI](#11-conexión-desde-power-bi)
12. [Incidencias y decisiones](#12-incidencias-y-decisiones)
13. [Identificadores de esta instalación](#13-identificadores-de-esta-instalación)
14. [Estado final y siguientes pasos](#14-estado-final-y-siguientes-pasos)
15. [Anexo: consulta rápida por API](#15-anexo-consulta-rápida-por-api)

---

## 1. Objetivo y resultado

El objetivo era conectar Dremio con la base `aeroflow` de MongoDB y preparar vistas SQL
que respondan a las preguntas D1–D9 del proyecto, con estas reglas comunes:

- métricas calculadas **solo sobre salidas válidas** (`record_valid = TRUE`);
- retraso en minutos entre `actual_departure_at` y `scheduled_departure_at`;
- superación del umbral cuando el retraso es **estrictamente mayor** que
  `delay_threshold_minutes`;
- agrupaciones temporales por **fecha/hora local de salida programada** en
  `Europe/Madrid`;
- puertas tomadas de la colección `operativos`, incluidas las que tienen cero salidas;
- filtro por `simulation_id` en el informe (las vistas exponen todas las simulaciones).

Resultado final:

| Elemento | Cantidad |
|---|---:|
| Fuentes MongoDB | 1 (`mongo_aeroflow`) |
| Espacios | 1 (`Aeroflow`) |
| Vistas base | 2 (`V0_salidas`, `V0_puertas`) |
| Vistas requeridas | 9 (`D1`–`D9`) |
| Vistas auxiliares | 2 (`D4b`, `D5b`) |
| **Datasets totales** | **13** |
| Salidas válidas de `SIM-01` | 1.007 |
| Salidas que superan el umbral | 374 (37,14 %) |
| Aviones distintos | 50 (50 con al menos una superación) |

Las 13 vistas compilan y consultan correctamente. Los totales de D2, D3, D4, D5, D5b,
D6 y D8 reconcilian con D9: **1.007 salidas válidas y 374 superaciones**.

> **Cambio respecto a la primera ejecución.** La primera pasada de `SIM-01` almacenó
> 1.020 salidas porque NiFi solo validaba el formato de `destination_id` y dejaba
> pasar 13 registros `DEST-UNKNOWN`. Se añadió la comprobación contra el catálogo
> `DEST-01…DEST-04`, se vació `SIM-01`, se reejecutó la simulación y ahora los 53
> defectos del generador (5 %) se rechazan. Las cifras de esta guía son las de la
> ejecución limpia.

---

## 2. Comprobaciones previas

En la VM `192.168.0.26` los servicios están instalados de forma nativa (sin Docker):

```bash
for s in kafka nifi mongod dremio; do
  printf "%-7s %-8s %-8s\n" "$s" "$(systemctl is-enabled $s)" "$(systemctl is-active $s)"
done
```

Resultado:

```text
kafka   enabled  active
nifi    enabled  active
mongod  enabled  active
dremio  enabled  active
```

Puertos implicados:

```bash
ss -ltnp | grep -E ':(9092|9095|8443|27017|9047)\b'
```

| Puerto | Servicio |
|---|---|
| `9092` | Kafka INTERNAL (PLAINTEXT) |
| `9095` | Kafka EXTERNAL (Traefik) |
| `8443` | NiFi HTTPS |
| `27017` | MongoDB |
| `9047` | Dremio |

Versiones comprobadas:

```bash
mongosh "mongodb://admin:<MONGO_ADMIN_PASSWORD>@localhost:27017/?authSource=admin" \
  --quiet --eval 'db.version()'
# 8.2.12

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9047/
# 200
```

La versión de Dremio se obtiene del login o de la UI: **26.0.5**
(`26.0.5-202509091642240013-f5051a07`).

Datos de partida en MongoDB:

```bash
mongosh "mongodb://admin:<MONGO_ADMIN_PASSWORD>@localhost:27017/?authSource=admin" --quiet --eval '
  const d = db.getSiblingDB("aeroflow");
  print("vuelos=" + d.vuelos.countDocuments());
  print("operativos=" + d.operativos.countDocuments());
  print("configuracion=" + d.configuracion.countDocuments());
  printjson(d.vuelos.aggregate([{ $group: { _id: "$simulation_id", n: { $sum: 1 } } }]).toArray());'
```

Resultado:

```text
vuelos=1109
operativos=4
configuracion=2
[
  { _id: 'SIM-NIFI-TEST', n: 1 },
  { _id: 'SIM-01', n: 1007 },
  { _id: 'SIM-POSTEND', n: 101 }
]
```

`SIM-01` es la simulación analizada. `SIM-NIFI-TEST` es el documento de prueba del flujo
NiFi y `SIM-POSTEND` es la simulación de evidencia post-fin; ambas se excluyen
filtrando por simulación. Tras el cambio de validación de destinos, `SIM-01` conserva
las 1.007 salidas válidas y los 53 defectos del generador quedan en el Funnel.

---

## 3. Acceso a Dremio y autenticación en la API

### 3.1. UI

- LAN: `http://192.168.0.26:9047`
- Traefik: `https://dremio.monolith.dynamic-dns.net`
- Usuario: `pablo`
- Contraseña: `<DREMIO_PASSWORD>`

### 3.2. Login por API

La API de Dremio usa `POST /apiv2/login` y devuelve un token:

```bash
DREMIO_URL=http://192.168.0.26:9047
TOKEN=$(curl -s -X POST "$DREMIO_URL/apiv2/login" \
  -H 'Content-Type: application/json' \
  -d '{"userName":"pablo","password":"<DREMIO_PASSWORD>"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

echo "$TOKEN"
```

Todas las llamadas siguientes llevan la cabecera:

```http
Authorization: _dremio<TOKEN>
```

> **Importante:** no hay espacio entre `_dremio` y el token. El token caduca; si una
> llamada devuelve `401`, hay que volver a hacer login.

### 3.3. Límite de resultados

El endpoint de resultados limita a **500 filas por página**:

```text
GET /api/v3/job/{id}/results?offset=0&limit=500
```

Si se pide `limit=2000`, Dremio responde:

```json
{"errorMessage": "limit can not exceed 500 rows"}
```

Para las vistas de este proyecto ninguna supera las 500 filas con `SIM-01` (D7 tiene
107 y D3 tiene 120), así que una sola página es suficiente. Para conjuntos mayores
habría que paginar con `offset`.

---

## 4. Creación de la fuente MongoDB

### 4.1. Creación desde la UI

1. Entrar en Dremio como `pablo`.
2. **Sources → Add source → MongoDB**.
3. Rellenar:
   - **Name:** `mongo_aeroflow`
   - **Connection Scheme:** `Standard (mongodb)`
   - **Host:** `localhost`
   - **Port:** `27017`
   - **Authentication:** `Master` (en esta versión, ver incidencia 12.2)
   - **Username:** `admin`
   - **Password:** `<MONGO_ADMIN_PASSWORD>`
   - **Authentication Database:** `admin`
   - **Encrypt connection:** desactivado (Mongo escucha en localhost)
4. Pulsar **Save**. Dremio debe mostrar `MongoDB is connected`.

> Si la UI de esta versión no ofrece la opción `Master` o no muestra el campo
> **Authentication Database**, usar la creación por API de la sección 4.2, que es la
> que se validó en esta instalación.

### 4.2. Creación por API

El payload exacto que funcionó fue:

```bash
curl -s -X POST "$DREMIO_URL/api/v3/source" \
  -H "Authorization: _dremio$TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "entityType": "source",
    "name": "mongo_aeroflow",
    "type": "MONGO",
    "config": {
      "connectionScheme": "STANDARD",
      "hostList": [{"hostname": "localhost", "port": 27017}],
      "username": "admin",
      "password": "<MONGO_ADMIN_PASSWORD>",
      "authenticationType": "MASTER",
      "authDatabase": "admin",
      "useSsl": false,
      "propertyList": [],
      "sampleSize": 4095,
      "sampleMethod": "FIRST",
      "authenticationTimeoutMillis": 2000,
      "secondaryReadsOnly": false,
      "useCaseInsensitiveFieldNames": false
    }
  }'
```

Respuesta (resumida):

```json
{
  "id": "9951e8d7-4d5f-4725-bf53-75ccc1b1aa88",
  "name": "mongo_aeroflow",
  "type": "MONGO"
}
```

Estado de la fuente:

```json
{
  "status": "good",
  "suggestedUserAction": "",
  "messages": [{"level": "INFO", "message": "MongoDB is connected"}]
}
```

### 4.3. Campos importantes del conector

| Campo | Valor usado | Motivo |
|---|---|---|
| `connectionScheme` | `STANDARD` | Conexión `mongodb://` directa, no `mongodb+srv://` |
| `hostList` | `[{"hostname":"localhost","port":27017}]` | El campo es `hostname`, no `host` |
| `username` | `admin` | Usuario administrador de MongoDB |
| `authenticationType` | `MASTER` | En el plugin de Mongo 26.0.5, es el modo que incorpora usuario/contraseña a la cadena |
| `authDatabase` | `admin` | Base de autenticación |
| `useSsl` | `false` | MongoDB local sin TLS |
| `sampleSize` | `4095` | Muestreo de esquema para inferir tipos |
| `sampleMethod` | `FIRST` | Suficiente para colecciones homogéneas |

> **Compatibilidad:** Dremio 26.0.5 incluye el driver de MongoDB 4.11.0 y conectó sin
> problemas con MongoDB 8.2.12. La fuente, las consultas y las vistas funcionan.

---

## 5. Exploración del catálogo y tipos de datos

La fuente descubre las bases de datos como contenedores y las colecciones como
datasets. No fue necesaria una promoción manual: las colecciones aparecen en el
catálogo y se pueden consultar por su ruta completa.

```bash
curl -s -H "Authorization: _dremio$TOKEN" \
  "$DREMIO_URL/api/v3/catalog/by-path/mongo_aeroflow/aeroflow"
```

Hijos:

```text
mongo_aeroflow.aeroflow.configuracion
mongo_aeroflow.aeroflow.operativos
mongo_aeroflow.aeroflow.vuelos
```

### 5.1. Esquema de `vuelos`

Consulta de comprobación:

```sql
SELECT * FROM mongo_aeroflow.aeroflow.vuelos LIMIT 2;
```

Tipos relevantes:

| Campo | Tipo Dremio | Uso |
|---|---|---|
| `event_id` | `VARCHAR` | Identificador único del evento |
| `operation_id` | `VARCHAR` | Identificador de la operación |
| `simulation_id` | `VARCHAR` | Filtro principal |
| `scheduled_departure_at` | `TIMESTAMP` | Fecha/hora UTC programada |
| `actual_departure_at` | `TIMESTAMP` | Fecha/hora UTC efectiva |
| `emitted_at` | `TIMESTAMP` | Emisión del evento |
| `gate_id` | `VARCHAR` | Puerta |
| `terminal_id` | `VARCHAR` | Terminal |
| `aircraft_id` | `VARCHAR` | Avión |
| `airline` | `VARCHAR` | Compañía |
| `aircraft_model` | `VARCHAR` | Modelo |
| `destination_id` | `VARCHAR` | Destino |
| `delay_threshold_minutes` | `INTEGER` | Umbral del escenario |
| `record_valid` | `BOOLEAN` | Validez del registro |
| `schema_version` | `INTEGER` | Versión del contrato |

### 5.2. Esquema de `operativos`

`gates` es una **lista de estructuras**:

```text
LIST<STRUCT<gate_id VARCHAR, name VARCHAR, terminal_id VARCHAR,
            delay_threshold_minutes INTEGER>>
```

Ejemplo para `SIM-01`:

```text
G1 / Puerta 1 / T1 / 15
G2 / Puerta 2 / T2 / 15
G3 / Puerta 3 / T3 / 15
G4 / Puerta 4 / T4 / 20
G5 / Puerta 5 / T5 / 15
```

> **Atención:** el umbral de G4 es **20**, no 15. Eso influye en su porcentaje de
> superación y debe mostrarse junto al indicador.

---

## 6. Decisiones de SQL y dialecto de Dremio

Antes de crear las vistas se probaron las funciones en el editor SQL de Dremio.
Estas son las decisiones que se aplicaron:

| Necesidad | Expresión usada | Comprobación |
|---|---|---|
| Retraso exacto | `TIMESTAMPDIFF(SECOND, ini, fin) / 60.0` | Devuelve `DOUBLE`; evita redondeos de minutos |
| Superación estricta | `... > delay_threshold_minutes` | 36 vuelos con retraso exactamente igual al umbral quedan fuera |
| Hora local | `CONVERT_TIMEZONE('UTC','Europe/Madrid', ts)` | Suma +2 h en octubre (CEST) |
| Fecha local | `CAST(ts_local AS DATE)` | Fecha de salida programada |
| Hora | `EXTRACT(HOUR FROM ts_local)` | 0–23 |
| Día de la semana | `EXTRACT(DOW FROM ts_local)` | **1 = domingo … 7 = sábado** |
| Fin de semana | `DOW IN (1,7)` | Sábado y domingo |
| Lista de puertas | `FLATTEN(gates)` | Una fila por puerta |
| Acceso a estructura | `t.gate.gate_id` | Necesita alias de subconsulta |
| División segura | `CASE WHEN denominador = 0 THEN 0 ...` | Evita división entre cero |
| Agregado condicional | `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` | Conteo de superaciones |
| Aviones con superación | `COUNT(DISTINCT CASE WHEN ... THEN aircraft_id END)` | Ignora `NULL` |

### 6.1. Precisión del retraso

El retraso se calcula en **segundos** y se divide entre 60:

```sql
TIMESTAMPDIFF(SECOND, scheduled_departure_at, actual_departure_at) / 60.0
```

Así, un retraso de 15 min 30 s es `15.5`, no `15` ni `16`. La comparación
`15.5 > 15` es correcta. Si se usara `TIMESTAMPDIFF(MINUTE, ...)`, Dremio truncaría
y podría clasificar mal operaciones cercanas al umbral.

### 6.2. Zona horaria

MongoDB guarda las fechas en UTC. La conversión se hace **solo para agrupar** por
hora, fecha y día de la semana:

```sql
CONVERT_TIMEZONE('UTC', 'Europe/Madrid', scheduled_departure_at)
```

En las fechas de `SIM-01` (5–11 de octubre de 2026) `Europe/Madrid` está en CEST
(UTC+2). Dremio aplica la base de datos de zonas horarias, por lo que el cambio de
horario de finales de octubre también sería correcto.

### 6.3. Día de la semana

`EXTRACT(DOW ...)` en Dremio devuelve:

```text
1 = domingo
2 = lunes
3 = martes
4 = miércoles
5 = jueves
6 = viernes
7 = sábado
```

Se verificó con el `2026-10-05` (lunes), que devuelve `2`. Por tanto:

```sql
CASE WHEN EXTRACT(DOW FROM scheduled_local) IN (1,7)
     THEN 'Fin de semana' ELSE 'Laborable' END
```

No se incorporan festivos, tal como pide el enunciado.

### 6.4. Listas y estructuras

`UNNEST` produjo errores internos en Dremio 26.0.5
(`ArrayIndexOutOfBoundsException` y problemas de alias). La solución estable fue
`FLATTEN` dentro de una subconsulta:

```sql
SELECT t.simulation_id, t.gate.gate_id
FROM (
  SELECT simulation_id, FLATTEN(gates) AS gate
  FROM mongo_aeroflow.aeroflow.operativos
) t
```

El acceso `t.gate.gate_id` funciona; `gate.gate_id` sin el alias de la subconsulta
fue interpretado como una tabla inexistente.

> **Naturaleza de los umbrales.** Los valores de `delay_threshold_minutes` son
> referencias didácticas del escenario, no criterios legales de compensación ni
> estándares oficiales de puntualidad. Las diferencias por compañía o modelo son
> descriptivas y no prueban causalidad.

---

## 7. Espacio `Aeroflow` y vistas base

### 7.1. Creación del espacio

```bash
curl -s -X POST "$DREMIO_URL/api/v3/catalog" \
  -H "Authorization: _dremio$TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"entityType":"space","name":"Aeroflow"}'
```

ID del espacio: `50a38725-de2b-457a-8421-944eee39353c`.

### 7.2. `V0_salidas`: enriquecimiento común

Esta vista concentra las reglas comunes para no repetirlas en D1–D9:

- filtra `record_valid = TRUE`;
- convierte la fecha programada a hora local;
- calcula fecha, hora y día de la semana locales;
- asigna franja horaria y tipo de día;
- calcula retraso, superación estricta y exceso sobre el umbral.

```sql
SELECT
  v.simulation_id, v.event_id, v.operation_id,
  v.scheduled_departure_at, v.actual_departure_at, v.emitted_at,
  v.terminal_id, v.gate_id, v.aircraft_id, v.flight_number,
  v.airline, v.aircraft_model, v.destination_id, v.delay_threshold_minutes,
  v.scheduled_local,
  CAST(v.scheduled_local AS DATE) AS scheduled_local_date,
  EXTRACT(HOUR FROM v.scheduled_local) AS local_hour,
  EXTRACT(DOW FROM v.scheduled_local) AS local_dow,
  CASE WHEN EXTRACT(HOUR FROM v.scheduled_local) < 6 THEN 'Madrugada (00-06)'
       WHEN EXTRACT(HOUR FROM v.scheduled_local) < 12 THEN 'Mañana (06-12)'
       WHEN EXTRACT(HOUR FROM v.scheduled_local) < 18 THEN 'Tarde (12-18)'
       ELSE 'Noche (18-24)' END AS time_band,
  CASE WHEN EXTRACT(DOW FROM v.scheduled_local) IN (1,7)
       THEN 'Fin de semana' ELSE 'Laborable' END AS day_type,
  TIMESTAMPDIFF(SECOND, v.scheduled_departure_at, v.actual_departure_at) / 60.0 AS delay_minutes,
  CASE WHEN TIMESTAMPDIFF(SECOND, v.scheduled_departure_at, v.actual_departure_at) / 60.0
            > v.delay_threshold_minutes
       THEN 1 ELSE 0 END AS exceeds_threshold,
  TIMESTAMPDIFF(SECOND, v.scheduled_departure_at, v.actual_departure_at) / 60.0
    - v.delay_threshold_minutes AS minutes_over_threshold
FROM (
  SELECT *, CONVERT_TIMEZONE('UTC','Europe/Madrid', scheduled_departure_at) AS scheduled_local
  FROM mongo_aeroflow.aeroflow.vuelos
  WHERE record_valid = TRUE
) v
```

Comprobación:

```sql
SELECT COUNT(*) AS salidas, COUNT(DISTINCT aircraft_id) AS aviones
FROM Aeroflow.V0_salidas
WHERE simulation_id = 'SIM-01';
```

Resultado: **1.007 salidas, 50 aviones**.

### 7.3. `V0_puertas`: universo de puertas

```sql
SELECT
  t.simulation_id,
  t.gate.gate_id AS gate_id,
  t.gate.name AS gate_name,
  t.gate.terminal_id AS terminal_id,
  t.gate.delay_threshold_minutes AS gate_threshold
FROM (
  SELECT simulation_id, FLATTEN(gates) AS gate
  FROM mongo_aeroflow.aeroflow.operativos
) t
```

Comprobación para `SIM-01`: **5 filas** (G1–G5), con umbral 15 salvo G4 = 20.

> Esta vista se usa con `LEFT JOIN` en D1, D2 y D6 para que las puertas sin salidas
> aparezcan con cero. En D3, D4, D5, D7, D8 y D9 las puertas sin salidas no generan
> filas porque las métricas se calculan sobre operaciones existentes.

---

## 8. Vistas D1–D9

Todas las vistas se crearon en el espacio `Aeroflow` con `sqlContext = ["Aeroflow"]`.
Los resultados que se muestran a continuación están filtrados por
`simulation_id = 'SIM-01'`.

### D1. Salidas válidas y aviones distintos por puerta y destino

**Pregunta:** ¿cuántas salidas válidas y cuántos aviones distintos se registran por
puerta y destino?

```sql
SELECT g.simulation_id, g.gate_id, g.terminal_id, v.destination_id,
       COUNT(v.event_id) AS valid_departures,
       COUNT(DISTINCT v.aircraft_id) AS distinct_aircraft
FROM Aeroflow.V0_puertas g
LEFT JOIN Aeroflow.V0_salidas v
  ON v.simulation_id = g.simulation_id AND v.gate_id = g.gate_id
GROUP BY g.simulation_id, g.gate_id, g.terminal_id, v.destination_id
```

- **Unidades:** salidas (operaciones) y aviones distintos.
- **Filtros:** `SIM-01`, `record_valid = TRUE`, unión por simulación y puerta.
- **Denominador:** no aplica; son recuentos.
- **Nota:** `COUNT(DISTINCT aircraft_id)` es correcto dentro de cada grupo, pero **no
  se puede sumar** entre grupos para obtener el total del aeropuerto. El total está en D9.

Resultado (20 filas: 5 puertas × 4 destinos del catálogo):

| Puerta | Terminal | Destino | Salidas válidas | Aviones distintos |
|---|---|---|---|---|
| G1 | T1 | DEST-01 | 51 | 33 |
| G1 | T1 | DEST-02 | 72 | 41 |
| G1 | T1 | DEST-03 | 83 | 43 |
| G1 | T1 | DEST-04 | 51 | 33 |
| G2 | T2 | DEST-01 | 40 | 29 |
| G2 | T2 | DEST-02 | 36 | 27 |
| G2 | T2 | DEST-03 | 67 | 38 |
| G2 | T2 | DEST-04 | 40 | 28 |
| G3 | T3 | DEST-01 | 39 | 29 |
| G3 | T3 | DEST-02 | 51 | 35 |
| G3 | T3 | DEST-03 | 72 | 40 |
| G3 | T3 | DEST-04 | 62 | 36 |
| G4 | T4 | DEST-01 | 46 | 32 |
| G4 | T4 | DEST-02 | 44 | 33 |
| G4 | T4 | DEST-03 | 65 | 38 |
| G4 | T4 | DEST-04 | 51 | 31 |
| G5 | T5 | DEST-01 | 37 | 25 |
| G5 | T5 | DEST-02 | 30 | 23 |
| G5 | T5 | DEST-03 | 39 | 28 |
| G5 | T5 | DEST-04 | 31 | 23 |

**Lectura:** G1 y G3 concentran el mayor volumen (257 y 224 salidas). DEST-03 es el
destino más frecuente (326 salidas), seguido de DEST-04 (235) y DEST-02 (233).
No aparecen destinos fuera del catálogo porque NiFi rechaza cualquier
`destination_id` que no sea `DEST-01`–`DEST-04`.

**Puertas con cero salidas:** se probó con `SIM-VALID-API`, que tiene configuración
en `operativos` pero ninguna salida. D1 devuelve las 5 puertas con
`valid_departures = 0`, `distinct_aircraft = 0` y `destination_id = NULL`. Es el
comportamiento esperado del `LEFT JOIN`.

### D2. Puertas con mayor porcentaje de superación

**Pregunta:** ¿qué puertas presentan mayor porcentaje de vuelos con retraso superior
al umbral?

```sql
SELECT g.simulation_id, g.gate_id, g.terminal_id, g.gate_threshold,
       COUNT(v.event_id) AS valid_departures,
       COALESCE(SUM(v.exceeds_threshold), 0) AS over_threshold,
       CASE WHEN COUNT(v.event_id) = 0 THEN 0.0
            ELSE COALESCE(SUM(v.exceeds_threshold), 0) * 100.0 / COUNT(v.event_id) END
         AS pct_over_threshold
FROM Aeroflow.V0_puertas g
LEFT JOIN Aeroflow.V0_salidas v
  ON v.simulation_id = g.simulation_id AND v.gate_id = g.gate_id
GROUP BY g.simulation_id, g.gate_id, g.terminal_id, g.gate_threshold
```

- **Unidades:** salidas y porcentaje.
- **Denominador:** total de salidas válidas de cada puerta.
- **Umbral:** el de cada vuelo (`delay_threshold_minutes`); `gate_threshold` es informativo.

| Puerta | Terminal | Umbral | Salidas válidas | Superan umbral | % |
|---|---|---|---|---|---|
| G4 | T4 | 20 | 206 | 128 | **62,14** |
| G1 | T1 | 15 | 257 | 93 | 36,19 |
| G3 | T3 | 15 | 224 | 68 | 30,36 |
| G2 | T2 | 15 | 183 | 50 | 27,32 |
| G5 | T5 | 15 | 137 | 35 | 25,55 |

**Lectura:** G4 tiene el porcentaje más alto (62,14 %), pero también un umbral más
exigente (20 min) y una composición de vuelos distinta. G1 es la puerta con más
salidas y el segundo porcentaje. G5 es la que menos supera, con 25,55 %.

La suma de salidas es 1.007 y la de superaciones 374, que coincide con D9.

### D3. Horas y franjas horarias

**Pregunta:** ¿en qué horas y franjas se concentran las superaciones?

```sql
SELECT simulation_id, gate_id, local_hour, time_band,
       COUNT(*) AS valid_departures,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, gate_id, local_hour, time_band
```

- **Unidades:** salidas y porcentaje.
- **Hora:** local de salida programada (`Europe/Madrid`), no la efectiva.
- **Franjas:** 00–06, 06–12, 12–18 y 18–24, sin solapamiento.
- **Filas:** 120 para `SIM-01` (5 puertas × 24 horas; todas las celdas tienen vuelos).

Resumen por franja:

| Franja | Salidas válidas | Superan umbral | % |
|---|---|---|---|
| Madrugada (00–06) | 185 | 59 | 31,89 |
| Mañana (06–12) | 301 | 102 | 33,89 |
| Tarde (12–18) | 286 | 94 | 32,87 |
| Noche (18–24) | 235 | 119 | **50,64** |

Top 10 celdas puerta–hora por porcentaje:

| Puerta | Hora local | Franja | Salidas válidas | Superan umbral | % |
|---|---|---|---|---|---|
| G4 | 20 | Noche | 14 | 14 | 100,00 |
| G5 | 20 | Noche | 2 | 2 | 100,00 |
| G1 | 18 | Noche | 6 | 5 | 83,33 |
| G4 | 7 | Mañana | 10 | 8 | 80,00 |
| G4 | 19 | Noche | 9 | 7 | 77,78 |
| G4 | 18 | Noche | 13 | 10 | 76,92 |
| G4 | 22 | Noche | 8 | 6 | 75,00 |
| G4 | 23 | Noche | 8 | 6 | 75,00 |
| G4 | 15 | Tarde | 11 | 8 | 72,73 |
| G4 | 5 | Madrugada | 7 | 5 | 71,43 |

**Lectura:** la franja de noche concentra el 50,64 % de superaciones, frente al
31–34 % de las demás. G4 es la puerta que más contribuye. Las celdas con muy pocas
salidas (por ejemplo, G5 a las 20 h con 2 vuelos) deben interpretarse con cautela:
un 100 % sobre 2 observaciones no es comparable a un 100 % sobre 14.

### D4. Días laborables y fin de semana

**Pregunta:** ¿qué diferencias aparecen entre días laborables y fin de semana?

```sql
SELECT simulation_id, day_type,
       COUNT(*) AS valid_departures,
       COUNT(DISTINCT aircraft_id) AS distinct_aircraft,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, day_type
```

- **Unidades:** salidas, aviones distintos y porcentaje.
- **Clasificación:** fecha local de salida programada; lunes–viernes laborable,
  sábado–domingo fin de semana; sin festivos.
- **Denominador:** salidas válidas de cada tipo de día.

| Tipo de día | Salidas válidas | Aviones distintos | Superan umbral | % |
|---|---|---|---|---|
| Fin de semana | 286 | 50 | 115 | **40,21** |
| Laborable | 721 | 50 | 259 | 35,92 |

**Lectura:** el fin de semana tiene menos salidas (2 días frente a 5), pero un
porcentaje de superación algo mayor (40,21 % vs 35,92 %). Los 50 aviones distintos
aparecen en ambos tipos de día; **no se suman** (son el mismo conjunto de aviones).
La comparación correcta es de porcentajes, no de totales absolutos.

Vista auxiliar `D4b_evolucion_diaria` para la evolución temporal de Power BI:

```sql
SELECT simulation_id, scheduled_local_date, day_type,
       COUNT(*) AS valid_departures,
       COUNT(DISTINCT aircraft_id) AS distinct_aircraft,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, scheduled_local_date, day_type
```

| Fecha local | Tipo | Salidas | Aviones | Superan | % |
|---|---|---|---|---|---|
| 2026-10-05 | Laborable | 151 | 50 | 51 | 33,77 |
| 2026-10-06 | Laborable | 138 | 50 | 57 | 41,30 |
| 2026-10-07 | Laborable | 144 | 50 | 50 | 34,72 |
| 2026-10-08 | Laborable | 143 | 50 | 53 | 37,06 |
| 2026-10-09 | Laborable | 145 | 50 | 48 | 33,10 |
| 2026-10-10 | Fin de semana | 146 | 50 | 51 | 34,93 |
| 2026-10-11 | Fin de semana | 140 | 50 | 64 | **45,71** |

El 11 de octubre es el día con mayor porcentaje (45,71 %), lo que explica en parte
la diferencia del agregado de fin de semana.

### D5. Compañías con mayor porcentaje de superación

**Pregunta:** ¿qué compañías presentan mayor porcentaje de vuelos con retraso superior
al umbral, con un mínimo de 100 salidas válidas?

```sql
SELECT simulation_id, airline,
       COUNT(*) AS valid_departures,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold,
       CASE WHEN COUNT(*) >= 100 THEN TRUE ELSE FALSE END AS meets_minimum
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, airline
```

- **Unidades:** salidas y porcentaje.
- **Denominador:** salidas válidas de cada compañía.
- **Umbral mínimo:** 100 salidas; `meets_minimum` permite separar la tabla de
  compañías clasificables de la de compañías por debajo del mínimo.
- **Compañías por debajo:** en `SIM-01` no hay ninguna; todas superan 100. Para otra
  simulación, filtrar `meets_minimum = FALSE` en Power BI.

| Compañía | Salidas válidas | Superan umbral | % | ≥100 |
|---|---|---|---|---|
| Aero03 | 100 | 43 | **43,00** | Sí |
| Aero01 | 100 | 41 | 41,00 | Sí |
| Aero08 | 101 | 39 | 38,61 | Sí |
| Aero09 | 101 | 39 | 38,61 | Sí |
| Aero02 | 100 | 38 | 38,00 | Sí |
| Aero04 | 101 | 38 | 37,62 | Sí |
| Aero05 | 101 | 37 | 36,63 | Sí |
| Aero07 | 101 | 35 | 34,65 | Sí |
| Aero06 | 101 | 32 | 31,68 | Sí |
| Aero10 | 101 | 32 | 31,68 | Sí |

**Lectura:** el rango va de 31,68 % (Aero06 y Aero10) a 43,00 % (Aero03), unas 11,3
puntos porcentuales. Todas las compañías están justo por encima de 100 salidas, por
lo que una o dos operaciones pueden mover el porcentaje. No se debe interpretar como
una diferencia causal de comportamiento: la composición de destinos, puertas, modelos
y franjas puede explicar parte de la variación.

Vista auxiliar `D5b_companias_por_puerta` para comparar la composición:

```sql
SELECT simulation_id, airline, gate_id,
       COUNT(*) AS valid_departures,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, airline, gate_id
```

Muestra (grupos con al menos 15 salidas; no se aplica el mínimo de 100 porque el
objetivo es descriptivo, no clasificar compañías):

| Compañía | Puerta | Salidas | Superan | % |
|---|---|---|---|---|
| Aero07 | G4 | 18 | 14 | 77,78 |
| Aero10 | G4 | 20 | 15 | 75,00 |
| Aero03 | G4 | 25 | 18 | 72,00 |
| Aero01 | G4 | 24 | 16 | 66,67 |
| Aero05 | G4 | 15 | 10 | 66,67 |
| Aero04 | G4 | 26 | 16 | 61,54 |
| Aero10 | G2 | 23 | 2 | 8,70 |
| Aero10 | G3 | 25 | 3 | 12,00 |
| Aero04 | G5 | 22 | 3 | 13,64 |

La puerta G4 aparece sistemáticamente por encima del resto, lo que sugiere que el
efecto de puerta pesa más que la compañía en esta simulación. Se muestran también
tres grupos del extremo inferior (Aero10 en G2/G3 y Aero04 en G5) para contraste.

### D6. Retraso medio y magnitud de la superación

**Pregunta:** ¿cómo varían el retraso medio y la magnitud de la superación por puerta
y destino?

```sql
SELECT g.simulation_id, g.gate_id, g.terminal_id, v.destination_id,
       COUNT(v.event_id) AS valid_departures,
       AVG(v.delay_minutes) AS avg_delay_minutes,
       COALESCE(SUM(v.exceeds_threshold), 0) AS over_threshold,
       AVG(CASE WHEN v.exceeds_threshold = 1 THEN v.minutes_over_threshold END)
         AS avg_minutes_over,
       MAX(CASE WHEN v.exceeds_threshold = 1 THEN v.minutes_over_threshold END)
         AS max_minutes_over,
       CASE WHEN COUNT(v.event_id) = 0 THEN 'Sin salidas'
            WHEN COALESCE(SUM(v.exceeds_threshold), 0) = 0 THEN 'Sin superaciones'
            ELSE 'Con superaciones' END AS note
FROM Aeroflow.V0_puertas g
LEFT JOIN Aeroflow.V0_salidas v
  ON v.simulation_id = g.simulation_id AND v.gate_id = g.gate_id
GROUP BY g.simulation_id, g.gate_id, g.terminal_id, v.destination_id
```

- **Unidades:** minutos y salidas.
- **Retraso medio:** sobre **todas** las salidas válidas del grupo.
- **Media y máximo del exceso:** solo sobre las que superan el umbral; el exceso es
  `delay_minutes - delay_threshold_minutes`.
- **Sin superaciones:** `note = 'Sin superaciones'` y los campos de exceso quedan a
  `NULL` (no se inventa un 0).
- **Sin salidas:** `note = 'Sin salidas'` (puerta del universo `operativos` sin vuelos).

Grupos con más salidas:

| Puerta | Destino | Salidas | Retraso medio | Superan | Media exceso | Máx. exceso | Nota |
|---|---|---|---|---|---|---|---|
| G1 | DEST-03 | 83 | 21,60 | 28 | 35,11 | 60 | Con superaciones |
| G1 | DEST-02 | 72 | 26,82 | 35 | 31,26 | 58 | Con superaciones |
| G3 | DEST-03 | 72 | 19,21 | 21 | 31,95 | 59 | Con superaciones |
| G2 | DEST-03 | 67 | 15,27 | 15 | 26,73 | 58 | Con superaciones |
| G4 | DEST-03 | 65 | 30,68 | 37 | 27,32 | 58 | Con superaciones |
| G3 | DEST-04 | 62 | 19,13 | 16 | 39,50 | 60 | Con superaciones |
| G1 | DEST-01 | 51 | 15,90 | 15 | 20,80 | 48 | Con superaciones |
| G1 | DEST-04 | 51 | 17,24 | 15 | 24,67 | 60 | Con superaciones |

Todos los grupos del catálogo tienen al menos una superación en `SIM-01`; no hay
filas con `note = 'Sin superaciones'`. La comprobación de que el flujo etiqueta
correctamente esos casos se hace sobre `SIM-VALID-API` y sobre los grupos con cero
salidas (sección 9).

**Lectura:** G4–DEST-02 tiene el retraso medio más alto (43,77 min) y 36
superaciones. G1–DEST-03 es el grupo con más salidas (83) y un retraso medio de
21,60 min. G5–DEST-03 es el grupo con menor retraso medio (9,64 min) y solo 4
superaciones.

### D7. Aviones con dos o más superaciones en un mismo día

**Pregunta:** ¿qué aviones registran dos o más operaciones con retraso superior al
umbral durante un mismo día?

```sql
SELECT simulation_id, aircraft_id, scheduled_local_date,
       COUNT(DISTINCT operation_id) AS operations,
       COUNT(*) AS over_threshold_departures,
       MAX(minutes_over_threshold) AS max_minutes_over
FROM Aeroflow.V0_salidas
WHERE exceeds_threshold = 1
GROUP BY simulation_id, aircraft_id, scheduled_local_date
HAVING COUNT(DISTINCT operation_id) >= 2
```

- **Unidades:** operaciones, salidas y minutos.
- **Fecha:** local de salida programada.
- **Operación distinta:** `COUNT(DISTINCT operation_id)`; no se agrupa por `event_id`
  para evitar duplicados de una misma operación.
- **Condición:** `HAVING >= 2`; un avión con una sola superación en días distintos no
  aparece.

Resultado: **107 grupos avión-día** (91 con 2 operaciones y 16 con 3), 44 aviones
distintos y 230 salidas con superación dentro de estos grupos. Las otras 144
superaciones de `SIM-01` son casos aislados de avión-día y no cumplen la condición.

Top 10 por máxima diferencia:

| Avión | Fecha local | Operaciones | Superan umbral | Máx. exceso (min) |
|---|---|---|---|---|
| AV-0010 | 2026-10-05 | 2 | 2 | 60 |
| AV-0014 | 2026-10-09 | 2 | 2 | 60 |
| AV-0031 | 2026-10-06 | 2 | 2 | 60 |
| AV-0037 | 2026-10-11 | 2 | 2 | 60 |
| AV-0003 | 2026-10-10 | 2 | 2 | 59 |
| AV-0029 | 2026-10-09 | 3 | 3 | 59 |
| AV-0039 | 2026-10-06 | 2 | 2 | 59 |
| AV-0022 | 2026-10-11 | 2 | 2 | 58 |
| AV-0025 | 2026-10-10 | 2 | 2 | 58 |
| AV-0031 | 2026-10-05 | 2 | 2 | 58 |

**Lectura:** el avión AV-0029 acumula 3 operaciones con superación el 2026-10-09;
AV-0031 aparece en dos días distintos, lo que es válido porque la condición es por
día. La máxima diferencia observada en estos grupos es 60 min.

### D8. Modelos por compañía

**Pregunta:** ¿qué modelos presentan mayor porcentaje de superación dentro de cada
compañía, con un mínimo de 100 salidas por combinación?

```sql
SELECT simulation_id, airline, aircraft_model,
       COUNT(*) AS valid_departures,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold,
       CASE WHEN COUNT(*) >= 100 THEN TRUE ELSE FALSE END AS meets_minimum
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, airline, aircraft_model
```

- **Unidades:** salidas y porcentaje.
- **Denominador:** salidas válidas de cada combinación compañía–modelo.
- **Mínimo:** 100 salidas; `meets_minimum = FALSE` identifica las combinaciones que
  deben ir en la tabla aparte.
- **Filas:** 10 para `SIM-01`; cada compañía opera un solo modelo en esta simulación.

| Compañía | Modelo | Salidas válidas | Superan umbral | % | ≥100 |
|---|---|---|---|---|---|
| Aero01 | Modelo A | 100 | 41 | 41,00 | Sí |
| Aero02 | Modelo B | 100 | 38 | 38,00 | Sí |
| Aero03 | Modelo C | 100 | 43 | 43,00 | Sí |
| Aero04 | Modelo D | 101 | 38 | 37,62 | Sí |
| Aero05 | Modelo E | 101 | 37 | 36,63 | Sí |
| Aero06 | Modelo A | 101 | 32 | 31,68 | Sí |
| Aero07 | Modelo B | 101 | 35 | 34,65 | Sí |
| Aero08 | Modelo C | 101 | 39 | 38,61 | Sí |
| Aero09 | Modelo D | 101 | 39 | 38,61 | Sí |
| Aero10 | Modelo E | 101 | 32 | 31,68 | Sí |

**Lectura:** Aero03–Modelo C tiene el porcentaje más alto (43,00 %) y Aero06/Aero10
con Modelo A/E el más bajo (31,68 %). Como cada compañía usa un único modelo, en esta
simulación **no se puede separar el efecto compañía del efecto modelo**: están
confundidos. Se necesitaría una simulación con varios modelos por compañía para
comparar dentro de una misma compañía.

### D9. Proporción de aviones con al menos una superación

**Pregunta:** ¿qué proporción de aviones distintos presenta al menos una operación con
retraso superior al umbral?

```sql
SELECT simulation_id,
       COUNT(*) AS valid_departures,
       COUNT(DISTINCT aircraft_id) AS distinct_aircraft,
       COUNT(DISTINCT CASE WHEN exceeds_threshold = 1 THEN aircraft_id END)
         AS aircraft_with_exceedance,
       SUM(exceeds_threshold) AS over_threshold_departures,
       COUNT(DISTINCT CASE WHEN exceeds_threshold = 1 THEN aircraft_id END) * 100.0
         / COUNT(DISTINCT aircraft_id) AS pct_aircraft_with_exceedance,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_departures_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id
```

| Salidas válidas | Aviones distintos | Aviones con ≥1 superación | Salidas que superan | % aviones | % salidas |
|---:|---:|---:|---:|---:|---:|
| 1.007 | 50 | 50 | 374 | **100,00** | **37,14** |

**Lectura:** los 50 aviones tienen al menos una superación, pero solo el 37,14 % de
las salidas supera el umbral. No son contradictorios: un mismo avión puede acumular
varias superaciones. El porcentaje de aviones es 100 % porque el conjunto es pequeño
y todos los aviones vuelan varias veces; el de salidas mide la proporción de
operaciones, no de aviones.

---

## 9. Reconciliación y pruebas de validación

### 9.1. Totales

| Vista | Salidas válidas | Superan umbral | % |
|---|---:|---:|---:|
| D2 | 1.007 | 374 | 37,14 |
| D3 | 1.007 | 374 | 37,14 |
| D4 | 1.007 | 374 | 37,14 |
| D5 | 1.007 | 374 | 37,14 |
| D5b | 1.007 | 374 | 37,14 |
| D6 | 1.007 | 374 | 37,14 |
| D8 | 1.007 | 374 | 37,14 |
| D9 | 1.007 | 374 | 37,14 |

D1 también suma 1.007 salidas (no calcula superaciones). La coherencia entre todas
las vistas confirma que los `JOIN`, los filtros y los denominadores son correctos.

### 9.2. Superación estricta

Se buscaron vuelos con retraso **exactamente igual** al umbral:

```sql
SELECT event_id, gate_id, delay_minutes, delay_threshold_minutes,
       exceeds_threshold, minutes_over_threshold
FROM Aeroflow.V0_salidas
WHERE simulation_id = 'SIM-01'
  AND delay_minutes = delay_threshold_minutes
ORDER BY event_id
LIMIT 5;
```

Ejemplo:

```text
EV-SIM-01-000027 | G2 | 15.0 | 15 | 0 | 0.0
```

Hay **36 vuelos** con retraso igual al umbral y **ninguno** está marcado como
superación (`n_over = 0`). Esto valida la regla de `>` estricto.

### 9.3. Puertas con cero salidas

Consulta sobre `SIM-VALID-API` (configuración en `operativos`, sin vuelos):

```sql
SELECT * FROM Aeroflow.D1_salidas_por_puerta_destino
WHERE simulation_id = 'SIM-VALID-API';
```

Devuelve 5 filas, una por puerta, con `valid_departures = 0`,
`distinct_aircraft = 0` y `destination_id = NULL`.

D2 devuelve las 5 puertas con `pct_over_threshold = 0.0`, y D6 devuelve
`note = 'Sin salidas'`. No hay división entre cero.

### 9.4. Grupos sin superaciones

En la ejecución limpia de `SIM-01` todos los grupos puerta–destino tienen al menos una
superación, así que D6 no devuelve filas con `note = 'Sin superaciones'`. La rama
`CASE` está implementada y se comprueba con `SIM-VALID-API` (grupos con
`note = 'Sin salidas'`); para un grupo con salidas pero ninguna superación, la vista
devuelve `note = 'Sin superaciones'` y deja `avg_minutes_over` y `max_minutes_over` a
`NULL`.

### 9.5. Simulación de prueba

`SIM-NIFI-TEST` tiene 1 vuelo y no tiene documento en `operativos`. Por eso no
aparece en D1/D2/D6 (no hay puertas configuradas) y sí aparece en D5/D8/D9 como una
simulación de 1 salida si no se filtra. El informe debe filtrar por `SIM-01`; las
vistas no imponen una simulación fija para que Power BI pueda cambiar de escenario.

### 9.6. Evidencia de salida posterior al fin del periodo

`SIM-POSTEND` es una simulación pequeña y separada, creada solo para demostrar que
una operación programada dentro del periodo puede tener salida efectiva después del
fin. No forma parte del análisis D1–D9 de `SIM-01`.

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

Resultado: **3 salidas** cruzan el fin del periodo.

| `event_id` | Puerta | Destino | Salida programada | Salida efectiva | Retraso | Umbral |
|---|---|---|---|---|---|---|
| `EV-SIM-POSTEND-000033` | G2 | DEST-02 | 2026-10-11 10:50 | 2026-10-12 00:01 | 791 min | 15 |
| `EV-SIM-POSTEND-000078` | G1 | DEST-03 | 2026-10-11 15:01 | 2026-10-12 02:20 | 679 min | 15 |
| `EV-SIM-POSTEND-000100` | G2 | DEST-02 | 2026-10-11 22:37 | 2026-10-12 20:37 | 1320 min | 15 |

La simulación tiene **101 salidas válidas**, **5 aviones** y **101 superaciones**
(se configuró con `base_delay_probability = 1.0`). El detalle de su construcción está
en `GUIDE-simulacion-postend.md`. El informe de Power BI debe seguir filtrando
`SIM-01`; `SIM-POSTEND` solo se usa en la página de validación si se quiere mostrar
la evidencia.

---

## 10. Gestión de vistas por API

### 10.1. Crear una vista

```bash
curl -s -X POST "$DREMIO_URL/api/v3/catalog" \
  -H "Authorization: _dremio$TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "entityType": "dataset",
    "path": ["Aeroflow", "D1_salidas_por_puerta_destino"],
    "type": "VIRTUAL_DATASET",
    "sql": "SELECT ...",
    "sqlContext": ["Aeroflow"]
  }'
```

### 10.2. Actualizar una vista

Hay que enviar el `tag` actual (control de concurrencia):

```bash
DATASET_ID=<id>
TAG=$(curl -s -H "Authorization: _dremio$TOKEN" \
  "$DREMIO_URL/api/v3/catalog/$DATASET_ID" | python3 -c 'import sys,json;print(json.load(sys.stdin)["tag"])')

curl -s -X PUT "$DREMIO_URL/api/v3/catalog/$DATASET_ID" \
  -H "Authorization: _dremio$TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{
    \"entityType\": \"dataset\",
    \"id\": \"$DATASET_ID\",
    \"path\": [\"Aeroflow\", \"D1_salidas_por_puerta_destino\"],
    \"tag\": \"$TAG\",
    \"type\": \"VIRTUAL_DATASET\",
    \"sql\": \"SELECT ...\",
    \"sqlContext\": [\"Aeroflow\"]
  }"
```

### 10.3. Borrar una vista

```bash
curl -s -X DELETE "$DREMIO_URL/api/v3/catalog/$DATASET_ID?version=$TAG" \
  -H "Authorization: _dremio$TOKEN"
```

### 10.4. Idempotencia

Antes de crear una vista conviene comprobar si ya existe:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: _dremio$TOKEN" \
  "$DREMIO_URL/api/v3/catalog/by-path/Aeroflow/D1_salidas_por_puerta_destino"
# 200 = existe; 404 = no existe
```

Si se intenta crear una vista con un nombre existente, Dremio devuelve error. En ese
caso, actualizar con `PUT` o borrar y volver a crear.

---

## 11. Conexión desde Power BI

### 11.1. Conexión

- **Servidor:** `http://192.168.0.26:9047` (LAN) o `https://dremio.monolith.dynamic-dns.net`
- **Usuario:** `pablo`
- **Contraseña:** `<DREMIO_PASSWORD>`
- **Conector:** Dremio (si no está instalado, instalar el conector oficial)
- **Modo:** **DirectQuery**

Seleccionar el espacio `Aeroflow` y las vistas D1–D9 (y las auxiliares D4b/D5b si se
usan). No seleccionar las colecciones crudas de MongoDB para el informe: las vistas ya
aplican las reglas y los agregados.

> **Comprobación realizada:** el conector de Power BI instalado en el equipo de
> prácticas conecta con Dremio 26.0.5 y permite **DirectQuery** sobre las vistas
> `Aeroflow`. La prueba se hizo con `Aeroflow.D9_aviones_con_superacion`. No se
> sustituyó ningún componente.

### 11.2. Filtros del informe

| Filtro | Campo | Uso |
|---|---|---|
| Simulación | `simulation_id` | Filtro principal; `SIM-01` para el análisis |
| Fecha programada | `scheduled_local_date` | Evolución y comparaciones |
| Puerta | `gate_id` | Esquema y comparaciones |
| Destino | `destination_id` | D1/D6 |
| Compañía | `airline` | D5/D8 |
| Modelo | `aircraft_model` | D8 |
| Tipo de día | `day_type` | D4 |

### 11.3. Correspondencia con las páginas del informe

| Página | Visual | Vista |
|---|---|---|
| Estado general | Tarjetas de salidas, aviones, superaciones y % | D9 |
| Estado general | Esquema de puertas y barras de % | D2 (y D1 para volumen) |
| Patrones temporales | Mapa de calor puerta–hora | D3 |
| Patrones temporales | Evolución temporal | D4b |
| Patrones temporales | Comparación por destino y tipo de día | D4/D6 |
| Compañías y aviones | Barras de % con tamaño de muestra | D5 |
| Compañías y aviones | Tabla de compañías bajo el mínimo | D5 con `meets_minimum = FALSE` |
| Compañías y aviones | Comparación por puerta | D5b |
| Compañías y aviones | Modelos por compañía | D8 |
| Compañías y aviones | Aviones con 2+ superaciones/día | D7 |
| Compañías y aviones | % aviones vs % salidas | D9 |

### 11.4. Refresco

- En **DirectQuery**, cada visual consulta Dremio al abrir la página o al cambiar un
  filtro; no se importa una copia completa.
- El botón **Refresh** de Power BI vuelve a ejecutar las consultas.
- Un nuevo documento insertado en MongoDB aparece en la siguiente consulta de la
  vista (sujeto a la caché de metadatos de Dremio).
- Si se añaden campos o colecciones nuevas, refrescar los metadatos de la fuente en
  Dremio (**Source → Refresh metadata**) antes de usarlos.
- No se exige refresco automático cada segundo.

### 11.5. Cuidado con los aviones distintos

`COUNT(DISTINCT aircraft_id)` no es aditivo entre grupos. No se debe sumar la columna
`distinct_aircraft` de D1, D2 o D4 para obtener el total del aeropuerto: el mismo avión
puede aparecer en varias puertas, destinos o días. El total correcto está en D9
(`distinct_aircraft`). En Power BI, usar D9 para las tarjetas de aviones y D1/D2/D4
solo para comparar dentro de cada grupo.

---

## 12. Incidencias y decisiones

### 12.1. `hostList[0].host` inválido

El primer intento de crear la fuente usó:

```json
"hostList": [{"host": "localhost", "port": 27017}]
```

Dremio respondió:

```json
{"errorMessage":"Invalid value found at: hostList[0].host"}
```

El campo correcto es **`hostname`**:

```json
"hostList": [{"hostname": "localhost", "port": 27017}]
```

Se comprobó inspeccionando la clase `com.dremio.exec.catalog.conf.Host` del jar de
Dremio: sus campos son `hostname` y `port`.

### 12.2. `authenticationType: USER` no autenticaba

Con `USER`, la creación falló con:

```text
Command listDatabases requires authentication
```

El plugin de MongoDB de Dremio 26.0.5 solo incorpora usuario/contraseña a la cadena
de conexión cuando `authenticationType` es **`MASTER`**. Con `MASTER` la fuente
conectó y mostró `MongoDB is connected`.

### 12.3. `UNNEST` inestable

`CROSS JOIN UNNEST(gates)` produjo:

```text
java.lang.RuntimeException: ... DremioFieldTrimmer.trimFields ...
ArrayIndexOutOfBoundsException
```

La alternativa estable fue `FLATTEN(gates)` en una subconsulta y acceso
`t.gate.gate_id`. También funciona `t.gate['gate_id']`.

### 12.4. Límite de 500 filas

El endpoint de resultados no acepta `limit` mayor que 500. Las vistas de este
proyecto caben en una página, pero para D7 completo (107 filas) y D3 (120) también.
Si se consultan todas las simulaciones, paginar con `offset`.

### 12.5. `DOW` de Dremio

`EXTRACT(DOW ...)` devuelve 1 para domingo y 7 para sábado. Se verificó con
`2026-10-05` (lunes) = 2. No confundir con PostgreSQL, donde `DOW` devuelve 0 para
domingo.

### 12.6. Caracteres UTF-8

Las etiquetas `Mañana`, `Fin de semana`, etc. se almacenan y devuelven correctamente.
La etiqueta inicial `Manana` se corrigió a `Mañana` con un `PUT` de la vista
`V0_salidas`; las vistas dependientes se recalcularon sin cambios numéricos.

### 12.7. `DEST-UNKNOWN`

En la primera ejecución, NiFi solo validaba el **formato** de `destination_id` y 13
registros con `DEST-UNKNOWN` entraban en `vuelos` (1.020 salidas en total). Se
consideró incoherente con los 53 defectos del generador y con el catálogo de
`operativos`, así que se añadió a `ClasificarVuelo` la condición
`destination_id IN ('DEST-01','DEST-02','DEST-03','DEST-04')`. Después se vació
`SIM-01`, se reejecutó la simulación y ahora los 53 defectos se rechazan: **1.007
salidas válidas**, sin `DEST-UNKNOWN`.

La lista es fija y coincide con el catálogo del escenario. El modelo Pydantic y
`POST /api/configurations` rechazan cualquier configuración con otros destinos, de
modo que el formulario web no puede crear una simulación que NiFi vaya a rechazar
sistemáticamente. Si en el futuro se quisiera un catálogo variable, habría que
sustituir la lista por un `LookupRecord` contra `operativos`.

### 12.8. Simulación sin configuración

`SIM-NIFI-TEST` no tiene documento en `operativos`. Las vistas de puertas
(D1/D2/D6) no devuelven filas para esa simulación. Es correcto: sin configuración de
puertas no se puede construir el universo. Las simulaciones reales creadas por el
backend sí guardan su documento en `operativos`.

### 12.9. Token de Dremio

El token caduca. Si una llamada devuelve `401`, repetir el login. No se cachea el
token en el repositorio.

### 12.10. Contraseñas

No se escriben contraseñas en esta guía ni en el repositorio. La contraseña de
MongoDB está en `/root/.mongo_admin_pw` de la VM y la de Dremio se proporciona en el
aula. El archivo `.env` del backend está ignorado por git.

---

## 13. Identificadores de esta instalación

| Elemento | ID |
|---|---|
| Fuente `mongo_aeroflow` | `9951e8d7-4d5f-4725-bf53-75ccc1b1aa88` |
| Espacio `Aeroflow` | `50a38725-de2b-457a-8421-944eee39353c` |
| `V0_salidas` | `20017b5b-1257-4c88-8aee-4a056cdf6433` |
| `V0_puertas` | `3213b384-23ab-4f4a-b954-83f9ff912efa` |
| `D1_salidas_por_puerta_destino` | `093bf3f8-eb1b-4ec6-aeb6-48185b51bc85` |
| `D2_pct_sobre_umbral_puerta` | `2984fe30-3155-4874-9f4f-999f83774cb9` |
| `D3_horas_franjas` | `1116e24c-5eda-4ae3-ad06-dfc5bd3808a2` |
| `D4_laborables_fin_semana` | `12ae2493-c907-4c9d-b86a-5fb0b996a583` |
| `D4b_evolucion_diaria` | `fd19da50-e5d1-44b6-ae14-836bf2cea84b` |
| `D5_companias` | `8fc7797f-0f4d-4cea-87ac-8ae0324896bd` |
| `D5b_companias_por_puerta` | `4195d075-caf1-4e68-95b3-4b5e4c483d80` |
| `D6_retraso_medio_magnitud` | `0656f44a-9120-447d-8df0-97e661dcd9de` |
| `D7_aviones_repetidos_dia` | `ec9c7fb6-8326-442b-9279-74ad70a815cb` |
| `D8_compania_modelo` | `3682ab97-397e-4b43-9659-5cda93cc102c` |
| `D9_aviones_con_superacion` | `ea4d75b1-f8f7-40a9-8b83-8be7263e37d6` |

Rutas de consulta:

```text
mongo_aeroflow.aeroflow.vuelos
mongo_aeroflow.aeroflow.operativos
mongo_aeroflow.aeroflow.configuracion
Aeroflow.V0_salidas
Aeroflow.V0_puertas
Aeroflow.D1_salidas_por_puerta_destino
...
Aeroflow.D9_aviones_con_superacion
```

---

## 14. Estado final y siguientes pasos

### Completado

- [x] Servicios nativos `kafka`, `nifi`, `mongod` y `dremio` activos.
- [x] Dremio 26.0.5 conectado a MongoDB 8.2.12.
- [x] Fuente `mongo_aeroflow` con estado `MongoDB is connected`.
- [x] Espacio `Aeroflow` creado.
- [x] Vistas base `V0_salidas` y `V0_puertas`.
- [x] Nueve vistas D1–D9 creadas y consultables.
- [x] Vistas auxiliares `D4b` y `D5b`.
- [x] Reconciliación de totales: 1.007 salidas y 374 superaciones.
- [x] Reejecución limpia tras rechazar los 13 `DEST-UNKNOWN` (53 defectos).
- [x] Prueba de `>` estricto: 36 vuelos en el umbral, 0 superaciones.
- [x] Prueba de puertas con cero salidas.
- [x] Prueba de grupos con cero salidas y de la rama “Sin superaciones”.
- [x] Documentación de dialecto, incidencias e identificadores.
- [x] Power BI conectado a las vistas de Dremio en DirectQuery (comprobado).
- [x] Evidencia post-fin con `SIM-POSTEND`: 3 salidas cruzan el fin del periodo.

### Pendiente

- [ ] Construir las tres páginas del informe Power BI (la conexión DirectQuery ya
  está verificada).
- [ ] Aplicación web (frontend + backend) contra MongoDB.
- [ ] Pruebas funcionales 1–6 del enunciado.
- [ ] Memoria en LaTeX y vídeo de demostración.
- [ ] Revisar que las vistas se mantienen tras un reinicio de Dremio (el catálogo es
  persistente, pero conviene comprobarlo antes de la entrega).

---

## 15. Anexo: consulta rápida por API

Script mínimo para lanzar una consulta y recoger resultados (sin dependencias externas):

```python
import json
import os
import time
import urllib.request

BASE = os.environ.get("DREMIO_URL", "http://192.168.0.26:9047")
USER = os.environ.get("DREMIO_USER", "pablo")
PASSWORD = os.environ["DREMIO_PASSWORD"]


def login():
    req = urllib.request.Request(
        BASE + "/apiv2/login",
        data=json.dumps({"userName": USER, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["token"]


TOKEN = login()


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": "_dremio" + TOKEN,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        content = r.read()
        return json.loads(content) if content else {}


def query(sql, limit=500):
    job = call("POST", "/api/v3/sql", {"sql": sql})
    jid = job["id"]
    while True:
        st = call("GET", f"/api/v3/job/{jid}")
        if st["jobState"] in {"COMPLETED", "FAILED", "CANCELED"}:
            break
        time.sleep(0.5)
    if st["jobState"] != "COMPLETED":
        raise RuntimeError(st.get("errorMessage"))
    return call("GET", f"/api/v3/job/{jid}/results?offset=0&limit={limit}")["rows"]


if __name__ == "__main__":
    rows = query("""
        SELECT simulation_id, valid_departures, distinct_aircraft,
               over_threshold_departures, pct_aircraft_with_exceedance,
               pct_departures_over_threshold
        FROM Aeroflow.D9_aviones_con_superacion
        WHERE simulation_id = 'SIM-01'
    """)
    print(json.dumps(rows, indent=2, ensure_ascii=False))
```

Uso:

```bash
export DREMIO_PASSWORD='<DREMIO_PASSWORD>'
python3 dremio_query.py
```

Salida esperada:

```json
[
  {
    "simulation_id": "SIM-01",
    "valid_departures": 1007,
    "distinct_aircraft": 50,
    "over_threshold_departures": 374,
    "pct_aircraft_with_exceedance": 100.0,
    "pct_departures_over_threshold": 37.14001986097319
  }
]
```

---

*Guía construida a partir de la instalación real del 2026-11-02. Las cifras
corresponden a la simulación `SIM-01` y a las vistas del espacio `Aeroflow`.*
