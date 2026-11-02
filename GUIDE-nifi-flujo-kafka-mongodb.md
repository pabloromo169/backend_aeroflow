# Guía: Flujo NiFi `ConsumeKafka → PutMongo` (aeroflow.configuracion)

Guía paso a paso para crear, **desde la interfaz web de Apache NiFi**, un flujo
que consume el topic Kafka `aeroflow.configuracion` y guarda cada mensaje como
documento en MongoDB.

- **NiFi:** `https://nifi.monolith.dynamic-dns.net/nifi` (nativo en `192.168.0.26`, HTTPS 8443)
- **Kafka:** `localhost:9092` (PLAINTEXT, listener INTERNAL de la propia máquina)
- **MongoDB:** `localhost:27017` (auth `admin`), base `aeroflow`, colección `configuracion`
- **Credenciales NiFi:** usuario `hadoop`, contraseña `hadoophadoop`

---

## 1. Requisitos previos

- NiFi sirviendo **HTTPS** (la API no emite tokens por HTTP: `409 Access tokens
  are only issued over HTTPS`). Ver `GUIDE-traefik-servicios-nativos-192.168.0.26.md`, sección 2.
- Kafka con el topic `aeroflow.configuracion` (auto-create activo).
- MongoDB en marcha con auth.

---

## 2. Entrar en NiFi

1. Abre el navegador en `https://nifi.monolith.dynamic-dns.net/nifi`.
2. Introduce usuario **`hadoop`** y contraseña **`hadoophadoop`**.
3. Aparece el **canvas** (lienzo) del *root process group*: fondo blanco con la
   barra inferior de operaciones (zoom, pan, etc.).

> Si ves la página de login en bucle, revisa que entras por el dominio con
> HTTPS y no por una IP/HTTP.

---

## 3. Estructura del flujo

```
ConsumeKafka ──success──▶ RouteOnAttribute ──configuration──▶ PutMongo
                         (unmatched → auto-terminado)   (success/failure → auto-terminados)
```

| Procesador | Tipo (a buscar en el diálogo) | Función |
|---|---|---|
| `ConsumeKafka` | `ConsumeKafka` | Lee el topic |
| `RouteOnAttribute` | `RouteOnAttribute` | Filtra por topic |
| `PutMongo` | `PutMongo` | Inserta en MongoDB |

Controller services (ambos en el mismo process group):

| Servicio | Tipo | Estado final |
|---|---|---|
| `localhost:9092` | `Kafka3ConnectionService` | ENABLED |
| `MongoDBControllerService` | `MongoDBControllerService` | ENABLED |

---

## 4. Crear los Controller Services

Los *controller services* (servicios) se gestionan desde el **engranaje** de la
esquina superior derecha del canvas. Se crean **antes** que los procesadores que
los usan.

### 4.1 Abrir el diálogo

1. En el canvas del root process group, haz clic en el **icono de engranaje ⚙**
   (arriba a la derecha) → se abre **"Controller Services"**.
2. Pulsa el botón **`+`** (arriba a la derecha del diálogo) → *Add Controller Service*.

### 4.2 Kafka Connection Service

1. En el buscador escribe **`Kafka3ConnectionService`** y selecciónalo → **Add**.
2. Se añade una fila llamada `Kafka3ConnectionService`. No hace falta configurar
   nada: `bootstrap.servers` sale por defecto como `localhost:9092` y
   `security.protocol=PLAINTEXT`, que es lo que queremos.
3. Pulsa el **rayo ⚡ (Enable)** de esa fila y confirma (*Enable*). El estado
   pasa por `ENABLING` y luego queda en **`ENABLED`** (icono verde).

### 4.3 MongoDBControllerService

1. Pulsa de nuevo **`+`**, busca **`MongoDBControllerService`** → **Add**.
2. Pulsa el **lápiz ✎ (Edit)** de la fila y rellena:
   - **Mongo URI:** `mongodb://admin:7sh8bzNcAb1Ff6QDBTOI@localhost:27017/?authSource=admin`
3. **Apply**.
4. Pulsa el **rayo ⚡ (Enable)** y confirma. Espera a que quede **`ENABLED`**.

> Si tras habilitar aparece algún aviso, déjalo abierto unos segundos: el paso
> `ENABLING → ENABLED` no es instantáneo. Puedes refrescar con el botón
> de recarga del diálogo.

5. Cierra el diálogo con **Close**.

---

## 5. Añadir los procesadores

Para crear un procesador: **arrastra** el icono del procesador desde la barra de
herramientas superior izquierda hasta el canvas, o **clic derecho** en el canvas
→ *Add Processor* (atajo: tecla `P`). En el buscador del diálogo escribe el tipo
y pulsa **Add**.

### 5.1 `ConsumeKafka`

1. Añade un procesador de tipo **`ConsumeKafka`** y llámalo `ConsumeKafka`.
2. **Doble clic** sobre él (o clic derecho → *Configure*) → pestaña **Settings**:
   - **Automatically Terminate Relationships:** deja las que vienen por defecto
     (no toques nada aún).
3. Pestaña **Properties**, y rellena:

   | Propiedad | Valor |
   |---|---|
   | **Kafka Connection Service** | `localhost:9092` (el servicio del paso 4.2) |
   | **Group ID** | `config` |
   | **Topic Format** | `names` |
   | **Topics** | `aeroflow.configuracion` |
   | **auto.offset.reset** | `latest` |
   | **Commit Offsets** | `true` |

4. **Apply**.

### 5.2 `RouteOnAttribute`

1. Añade un procesador de tipo **`RouteOnAttribute`**, nombrado `RouteOnAttribute`.
2. **Doble clic** → pestaña **Properties**:
   - **Routing Strategy:** `Route to Property name` (por defecto).
3. Añade una **nueva propiedad** con el botón **`+`** (abajo a la derecha de la
   tabla de propiedades):
   - Nombre: `configuration`
   - Valor: `${kafka.topic:equals("aeroflow.configuracion")}`
4. Pestaña **Settings** → en **Automatically Terminate Relationships** marca
   **`unmatched`** (para que la rama no usada no deje el procesador en rojo).
5. **Apply**.

> **Filtro por topic, no por header:** en NiFi 2.12 `ConsumeKafka` **no** expone
> los headers de Kafka (p.ej. `message_type`) como atributos. Solo expone
> `kafka.topic`, `kafka.offset`, `kafka.partition`, `kafka.timestamp`,
> `kafka.header.count`, etc. Como el consumo ya es exclusivo de
> `aeroflow.configuracion`, se rutea por `kafka.topic`.

### 5.3 `PutMongo`

1. Añade un procesador de tipo **`PutMongo`**, nombrado `PutMongo`.
2. **Doble clic** → pestaña **Properties**:

   | Propiedad | Valor |
   |---|---|
   | **Client Service** | `MongoDBControllerService` (el servicio del paso 4.3) |
   | **Mongo Database Name** | `aeroflow` |
   | **Mongo Collection Name** | `configuracion` |
   | **Mode** | `insert` |

3. Pestaña **Settings** → en **Automatically Terminate Relationships** marca
   **`success`** y **`failure`**.
4. **Apply**.

> Tras configurar y conectar todo (sección 6), el icono de advertencia amarillo
> de cada procesador debe desaparecer.

---

## 6. Crear las conexiones

Las conexiones se dibujan **arrastrando** desde la flecha/ancla de un procesador
hasta otro. Para que aparezcan las asas, pasa el ratón por encima del procesador.

### 6.1 `ConsumeKafka` → `RouteOnAttribute`

1. Arrastra desde el borde **derecho** del `ConsumeKafka` (aparece un icono de
   flecha →) hasta el borde **izquierdo** del `RouteOnAttribute`.
2. En el diálogo **Create Connection**, en *For Relationships* marca **`success`**.
3. **Add** (o **Apply**).

### 6.2 `RouteOnAttribute` → `PutMongo`

1. Arrastra desde el `RouteOnAttribute` hasta el `PutMongo`.
2. En **Create Connection**, marca la relación **`configuration`**.
3. Acepta. Deja los valores por defecto de cola (*back pressure* 10 000 objetos /
   1 GB, sin expiración).

---

## 7. Arrancar el flujo

1. Selecciona los **tres** procesadores (clic sobre el canvas y arrastra un
   rectángulo que los englobe, o `Ctrl`+clic en cada uno).
2. En la barra inferior, pulsa el **botón de Play ▶ (Start)**.
3. Los tres iconos cambian a **cuadrado de stop ⏹**, señal de que están
   corriendo. Los indicadores de advertencia deben desaparecer.

---

## 8. Verificación end-to-end

### 8.1 Producir un mensaje de configuración

Publica un mensaje en el topic (por ejemplo, reenviando uno existente):

```bash
ssh hadoop@192.168.0.26 'printf "{\"simulation_id\":\"SIM-TEST\"}\n" | \
  /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 --topic aeroflow.configuracion'
```

> El header no importa: el flujo rutea por **topic**, no por header.

### 8.2 Confirmar que llegó a MongoDB

```bash
ssh hadoop@192.168.0.26 'mongosh "mongodb://admin:7sh8bzNcAb1Ff6QDBTOI@localhost:27017/?authSource=admin" \
  --quiet --eval "print(\"docs:\", db.getSiblingDB(\"aeroflow\").configuracion.countDocuments())"'
```

### 8.3 Observar el flujo en la UI

- **Clic derecho** en un procesador → *View Data Provenance* para ver los
  eventos (qué FlowFiles entraron/salieron y con qué atributos).
- **Clic derecho** sobre una conexión → *List Queue* para inspeccionar los
  FlowFiles encolados y sus **atributos** (aquí se ve `kafka.topic`,
  `kafka.offset`, etc.).
- Clic derecho en el canvas → *Status History* para ver contadores de
  entrada/salida por procesador.

---

## 9. Resultado obtenido

```
ConsumeKafka | Running | errors: 0
RouteOnAttribute | Running | errors: 0
PutMongo | Running | errors: 0
MongoDBControllerService: ENABLED
```

Mensaje real de `SIM-01` insertado en `aeroflow.configuracion`:

```json
{
  "_id": "6acbf0fcb5de9fbea3524ac7",
  "simulation_id": "SIM-01",
  "name": "Aeropuerto simulado Bahía de Cádiz",
  "timezone": "Europe/Madrid",
  "simulation_start": "2026-10-05T00:00:00Z",
  "simulation_days": 7,
  "...": "..."
}
```

---

## 10. Notas y avisos

- **Orden de creación:** crea y habilita los *controller services* **antes** de
  configurar los procesadores que los usan; si no, no aparecerán en el
  desplegable correspondiente.
- **Auto-terminate:** cada relación que no se conecte debe marcarse en la
  pestaña **Settings** del procesador, o el procesador quedará "inválido"
  (icono amarillo) y no arrancará.
- **Duplicados:** `PutMongo` en modo `insert` **no** deduplica. Un mensaje
  re-producido (o re-procesado tras reiniciar sin offsets) genera un documento
  nuevo. Para idempotencia usa `Mode=update` + `Upsert=true` con una clave
  adecuada.
- **Offsets:** `auto.offset.reset=latest` ignora lo ya publicado; para leer lo
  histórico usa `earliest` (para el consumidor y vuelve a arrancarlo).
- **El header `message_type`** que emite el backend (aeroflow) **no** llega como
  atributo a NiFi 2.12. Si en el futuro hace falta distinguir configuration vs
  flight en un mismo topic, habría que enrutar por el contenido del mensaje o
  usar topics separados.
- Documento relacionado: `GUIDE-traefik-servicios-nativos-192.168.0.26.md`
  (instalación nativa + Traefik + HTTPS de NiFi).
