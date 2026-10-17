# Backend AeroFlow

Backend en Python 3.12 para el escenario AeroFlow. Incluye una API FastAPI y un emisor de eventos Kafka. Kafka, NiFi y MongoDB son servicios externos: este proyecto no instala ni configura esos productos.

## Preparar el entorno

En PowerShell, desde la raíz del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Para instalar las dependencias de prueba se usa `requirements-dev.txt`; las versiones resueltas en el entorno actual también se registran en `requirements-lock.txt`.

Edita `.env` para indicar las direcciones de Kafka y MongoDB. Los valores por defecto apuntan al servidor comunicado: Kafka en `kafka.monolith.dynamic-dns.net:443` con SSL y MongoDB en `mongodb.monolith.dynamic-dns.net:443` con TLS y `authSource=admin`. Introduce las credenciales MongoDB únicamente en `MONGODB_USERNAME` y `MONGODB_PASSWORD` locales; no las pongas en el URI, el código ni el repositorio. Si el certificado de Kafka usa una CA privada, especifica su archivo PEM con `KAFKA_SSL_CA_LOCATION`; tanto el productor como el consumidor de inspección la reutilizan. NiFi es una interfaz de navegador en `https://nifi.monolith.dynamic-dns.net`; este backend no invoca directamente su interfaz. El API crea los índices necesarios, inserta `SIM-01` únicamente si aún no existe y publica esa configuración inicial en `aeroflow.configuracion` para que NiFi la persista; si Kafka no responde en el arranque, el API arranca igual y solo registra un aviso.

## Arrancar

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Se usa un worker porque el estado y la coordinación de una ejecución viven en memoria. La interfaz interactiva de OpenAPI está en `http://127.0.0.1:8000/docs`.

## API

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/health` | Comprobación de vida del proceso API |
| `GET` | `/api/configurations?limit=100&offset=0` | Configuraciones paginadas |
| `GET` | `/api/simulations` | Selector de simulación con total de salidas almacenadas y última emisión |
| `GET` | `/api/configurations/{simulation_id}` | Lee una configuración |
| `POST` | `/api/configurations` | Crea una configuración nueva; el API asigna ID y semilla si no se indican |
| `GET` | `/api/simulations/{simulation_id}/summary` | Contadores por las cinco puertas, con puertas sin eventos incluidas |
| `GET` | `/api/simulations/{simulation_id}/flights?limit=20&offset=0` | Últimas salidas almacenadas, paginadas (máximo 200 por página) |
| `GET` | `/api/simulations/{simulation_id}/timeline?interval=hour` | Evolución de salidas por hora efectiva UTC (`hour` o `day`) |
| `POST` | `/api/simulations/{simulation_id}/start` | Publica la configuración y comienza esa simulación |
| `POST` | `/api/simulations/stop` | Solicita una parada ordenada entre eventos confirmados |
| `GET` | `/api/simulations/status` | Estado, progreso, timestamps y último error |
| `POST` | `/api/simulations/{simulation_id}/test-events` | Publica casos de prueba etiquetados para NiFi |

Ejemplo para iniciar la semilla:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/simulations/SIM-01/start
Invoke-RestMethod http://127.0.0.1:8000/api/simulations/status
```

La API devuelve solo las salidas que ya estén guardadas en MongoDB. Es posible que el contador de eventos publicados aumente antes que los contadores de MongoDB, porque NiFi realiza la persistencia por separado. Los registros normales incluyen `record_valid=true`; alrededor del 5% contiene valores deliberadamente defectuosos para validar y enrutar con NiFi. Los campos de fallo concreto no se añaden al contrato del evento.

### Inspeccionar mensajes Kafka en vivo

Con el entorno virtual activo y `.env` configurado, abre otra terminal en la raíz del proyecto y ejecuta:

```powershell
.\.venv\Scripts\python.exe .\scripts\consume_kafka.py
```

El consumidor muestra topic, partición, offset, key, cabeceras y JSON. Para escuchar solo los vuelos o solo las configuraciones, pasa el topic como argumento, por ejemplo `...consume_kafka.py aeroflow.vuelos`. Usa un `group.id` de inspección único y `auto.offset.reset=earliest` para no interferir con NiFi. Los mensajes publicados antes de arrancar este consumidor pueden estar disponibles según la política de retención del topic.

Arranca el consumidor **antes** de la simulación para ver todos los mensajes desde el principio. El control de la API es:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/simulations/SIM-01/start
Invoke-RestMethod http://127.0.0.1:8000/api/simulations/status
```

Detén una ejecución con `Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/simulations/stop`. El consumidor separado no modifica ni confirma offsets del grupo de NiFi.

Las credenciales de MongoDB permanecen en el backend. CORS acepta todos los orígenes sin credenciales, según el alcance de demostración acordado. El backend no incluye autenticación, autorización ni protección CSRF; no exponerlo sin añadir esos controles o restringirlo a una red de demostración.

## Eventos Kafka

- Vuelos: `aeroflow.vuelos`, JSON del contrato del documento, clave Kafka `aircraft_id`, cabeceras `message_type=flight` y `simulation_id`.
- Configuración: `aeroflow.configuracion`, se publica una vez al inicio de cada ejecución, con clave `simulation_id` y cabeceras identificativas. La configuración inicial `SIM-01` también se publica al arrancar el API para que NiFi la persista; NiFi debe insertar la configuración con un upsert idempotente por `simulation_id`, ya que el backend guarda la misma configuración de forma directa.
- Los IDs de evento y operación se derivan de la simulación y posición para repetir el mismo conjunto. Reejecutar el mismo `simulation_id` publica desde el principio; el índice único de `event_id` en MongoDB debe volver idempotente la ingestión.
- El backend usa un **pool de 5 productores Kafka** (`KAFKA_PRODUCER_POOL_SIZE`, por defecto 5) que escriben en el **mismo topic**. Cada evento se envía por turnos (round-robin) al siguiente productor. La publicación es síncrona (espera la confirmación antes de continuar), así que se conserva el orden de las llamadas aunque el mensaje salga por un productor distinto.
- Las operaciones generadas se ordenan por salida efectiva y se evita el solapamiento del mismo avión. Kafka garantiza orden únicamente dentro de una partición. Con clave por avión, no debe suponerse orden global del topic entre particiones.
- Al detener, el productor espera confirmación de Kafka para el mensaje en curso. Los fallos definitivos marcan la ejecución `failed`; no se saltan silenciosamente.
- El endpoint de casos de prueba publica JSON malformado, campos incompletos, `record_valid=false` y un evento reenviado con el mismo ID.

## Configuración y simulación

El seed tiene siete días simulados, cinco puertas G1–G5 enlazadas uno a uno a T1–T5, 10 compañías, 50 aviones (cinco por compañía), cinco modelos (cada combinación de compañía/modelo tiene una flota equilibrada), destinos didácticos y 1060 operaciones. El 5% fijo de operaciones de muestra se distribuye entre errores detectables: campo obligatorio ausente, destino desconocido, umbral negativo o una hora efectiva declarada anterior a la programada. Esos errores mantienen `record_valid=true` para que NiFi haga la validación real.

La misma configuración y semilla generan iguales horarios, retrasos, aviones, identificadores y defectos. El campo `emitted_at` se reemplaza durante la publicación por la hora real UTC, por lo que puede variar entre repeticiones. `simulation_days` debe ser al menos siete y los umbrales de puerta deben ser positivos (mínimo 1 minuto); volumen y probabilidad de retraso se ajustan por perfiles de puerta, destino y franja. No se configura comportamiento distinto por compañía.

Los formularios de configuración requieren los catálogos y listas descritos en el JSON de `SIM-01`; pueden omitir `simulation_id` y `random_seed` para que los genere el backend, o especificar una semilla para reproducir los datos. Cada configuración guardada queda en `operativos` y se conserva para resultados históricos.

## Pruebas

```powershell
python -m pytest -q
```

Las pruebas automatizadas cubren generación, determinismo, contratos HTTP y coordinación usando adaptadores simulados; no necesitan servicios Kafka/MongoDB activos.
