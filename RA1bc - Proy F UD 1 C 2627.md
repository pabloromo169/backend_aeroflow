# AeroFlow: monitorización de vuelos con Kafka, NiFi, MongoDB, una aplicación web, Dremio y Power BI

**5075. Big Data aplicado — 1ª Evaluación (RA 1 – CE b, c)**

**Unidad Didáctica 1. Estrategias de ingestión y almacenamiento de datos en Big Data**

Como miembros del equipo de ingeniería de datos de un aeropuerto ficticio, vuestro primer reto será desarrollar e implementar **AeroFlow**, una plataforma para recoger, almacenar, monitorizar y analizar los registros de salida de vuelos publicados por cinco terminales asociados a cinco puertas de embarque.

El proyecto tiene dos objetivos principales: en primer lugar, automatizar el flujo de datos desde los terminales simulados hasta MongoDB mediante Kafka y NiFi; en segundo lugar, utilizar esos datos para responder a una pregunta de investigación mediante Dremio y Power BI, complementando el análisis con una web de seguimiento de la actividad del aeropuerto.

> **¿En qué puertas, destinos y franjas horarias se concentra una mayor proporción de vuelos con retrasos superiores al umbral del escenario, y qué diferencias se observan entre las compañías aéreas?**

Para responder, los datos deberán recorrer la canalización completa. Las respuestas se obtendrán mediante consultas SQL en Dremio y se presentarán en Power BI.

La aplicación web responderá a una segunda pregunta:

> **¿Cómo podemos comprobar que los cinco terminales están enviando datos y que las salidas de los vuelos se están incorporando al almacén?**

Los aviones, compañías, identificadores, horarios y umbrales serán sintéticos. Los destinos podrán proceder de un catálogo didáctico. Se analizarán salidas y retrasos, sin gestionar pistas, tripulaciones, pasajeros, rutas aéreas ni asignaciones dinámicas de puertas.

Cada evento representará una operación de salida ya completada en el escenario simulado. No será necesario generar estados sucesivos de un vuelo ni actualizar sus datos conforme avance una operación. El panel web mostrará las últimas salidas registradas, no una planificación de vuelos pendientes.

A continuación, se muestra un ejemplo del mensaje emitido por un terminal:

```json
{
    "event_id": "EV-SIM01-000123",
    "schema_version": 1,
    "simulation_id": "SIM-01",
    "scheduled_departure_at": "2026-10-05T08:00:00Z",
    "actual_departure_at": "2026-10-05T08:25:00Z",
    "emitted_at": "2026-10-03T19:20:00Z",
    "terminal_id": "T2",
    "gate_id": "G2",
    "aircraft_id": "AV-0042",
    "operation_id": "OP-SIM01-0081",
    "flight_number": "AS104",
    "airline": "AeroSur",
    "aircraft_model": "Modelo A",
    "destination_id": "DEST-03",
    "delay_threshold_minutes": 15,
    "record_valid": true
}
```

MongoDB conservará el histórico de salidas y la configuración del aeropuerto. La web consultará esos datos a través de un backend. Dremio proporcionará las vistas SQL que alimentarán el cuadro de mando de Power BI en DirectQuery.

La configuración del aeropuerto se definirá inicialmente en un archivo JSON que leerá el simulador y se almacenará, mediante Kafka y NiFi, en una colección de MongoDB denominada `operativos`, con un documento por simulación. Recogerá las puertas, los terminales asignados, los destinos permitidos, los umbrales de retraso simulados y los parámetros de generación de datos.

Además, la aplicación web permitirá consultar y modificar esta configuración mediante un formulario, utilizando el backend para validar y guardar los cambios en MongoDB. El simulador leerá la configuración guardada antes de iniciar cada nueva simulación. Los cambios se aplicarán a las siguientes ejecuciones, conservando la configuración utilizada en las anteriores para interpretar correctamente sus resultados.

Como ejemplo, un documento de la colección `operativos` tendrá la siguiente estructura. Este JSON es un ejemplo inicial que deberá completarse con los parámetros necesarios para el simulador, como el catálogo de compañías y modelos de avión, los aviones ficticios y los parámetros de generación de vuelos y retrasos. Los umbrales son ficticios:

```json
{
    "simulation_id": "SIM-01",
    "name": "Aeropuerto simulado Bahía de Cádiz",
    "timezone": "Europe/Madrid",
    "simulation_start": "2026-10-05T00:00:00Z",
    "simulation_days": 7,
    "publish_interval_ms": 1000,
    "random_seed": 42,
    "destinations": [
        {"destination_id": "DEST-01", "name": "Destino Norte"},
        {"destination_id": "DEST-02", "name": "Destino Centro"},
        {"destination_id": "DEST-03", "name": "Destino Este"}
    ],
    "gates": [
        {
            "gate_id": "G1",
            "name": "Puerta 1",
            "terminal_id": "T1",
            "delay_threshold_minutes": 15
        },
        {
            "gate_id": "G2",
            "name": "Puerta 2",
            "terminal_id": "T2",
            "delay_threshold_minutes": 15
        },
        {
            "gate_id": "G3",
            "name": "Puerta 3",
            "terminal_id": "T3",
            "delay_threshold_minutes": 15
        },
        {
            "gate_id": "G4",
            "name": "Puerta 4",
            "terminal_id": "T4",
            "delay_threshold_minutes": 15
        },
        {
            "gate_id": "G5",
            "name": "Puerta 5",
            "terminal_id": "T5",
            "delay_threshold_minutes": 15
        }
    ]
}
```

El campo `publish_interval_ms` establece la pausa real entre mensajes; `simulation_days` indica los días simulados y `random_seed` permite reproducir la generación con el mismo código y configuración. El campo `simulation_id` relacionará este documento con las salidas de su ejecución.

Los terminales son fuentes de datos simuladas vinculadas a las puertas de embarque. No representan edificios del aeropuerto. Su función es equivalente a la de los drones en el proyecto de tráfico: publicar registros y permitir estudiar cómo llegan al almacén.

## Objetivos del Proyecto

- Configurar un simulador Python reproducible que genere registros de salida de cinco terminales y la configuración del aeropuerto.
- Configurar y desplegar Kafka para recibir los mensajes y distribuirlos a los consumidores.
- Orquestar con NiFi la ingestión, validación, transformación, tratamiento de errores y persistencia de los datos.
- Configurar MongoDB para conservar el histórico y la configuración, con índices y control de duplicados.
- Desarrollar una aplicación web que muestre las puertas, los terminales, las últimas salidas y la evolución de los datos.
- Integrar Dremio y elaborar nueve consultas dirigidas que permitan analizar puertas, horarios, destinos, aviones, compañías y modelos.
- Construir un cuadro de mando en Power BI conectado mediante DirectQuery a las vistas de Dremio.
- Demostrar el recorrido de los datos y responder a la pregunta central mediante conclusiones justificadas.

## Implementación técnica

### Arquitectura y responsabilidades

```text
Simulador Python → Kafka → NiFi → MongoDB → Dremio → Power BI
```

La web utilizará un acceso adicional:

```text
Navegador → API backend → MongoDB
```

| Tecnología | Función |
| --- | --- |
| Python | Simular el aeropuerto y publicar salidas y datos de configuración |
| Kafka | Recibir y distribuir los eventos |
| NiFi | Consumir, validar, transformar, separar errores e insertar documentos |
| MongoDB | Almacenar salidas y configuración |
| Dremio | Consultar MongoDB y preparar vistas SQL |
| Power BI | Consultar las vistas mediante DirectQuery y presentar el análisis |
| API backend | Proporcionar a la web consultas acotadas sobre MongoDB |
| Web | Mostrar el seguimiento de la actividad y la llegada de datos |

> **Aviso:** Comprobad al inicio la compatibilidad de MongoDB con vuestro Dremio y la disponibilidad de DirectQuery en la conexión de Power BI. Comunicad las incompatibilidades al profesorado antes de sustituir componentes.

### Escenario del aeropuerto

Definid cinco puertas ficticias, identificadas como G1, G2, G3, G4 y G5. Asignad los terminales T1 a T5 a esas puertas, respectivamente. La asignación permanecerá fija durante cada simulación.

Cada puerta dispondrá de un nombre y un umbral simulado de retraso. Todas las puertas podrán registrar salidas a cualquiera de los destinos del catálogo. Los umbrales permanecerán constantes durante cada ejecución.

Para simplificar las comparaciones, todos los registros corresponderán a vuelos de pasajeros completados. No se incluirán cancelaciones ni vuelos sin hora efectiva de salida. La salida efectiva no será anterior a la programada: los retrasos del escenario serán no negativos.

Definid una configuración reproducible con la semilla del generador, la duración simulada, las puertas, los terminales, los destinos, las compañías y modelos, y los parámetros de actividad y retraso. Todos los valores deberán documentarse. No es necesario utilizar datos de un aeropuerto real ni cartografía oficial: un esquema de las cinco puertas será suficiente.

### Python y Kafka: simulación y emisión de eventos

Desarrollad un productor Python, en script o cuaderno Jupyter, que genere eventos progresivamente. La velocidad de reproducción será configurable para que el tiempo simulado pueda avanzar más deprisa que el real.

El conjunto analítico abarcará al menos siete días simulados de salidas programadas, incluyendo días laborables y fin de semana, con actividad en las distintas franjas horarias. Las siete jornadas no requieren mantener el programa funcionando durante siete días reales. Publicad también las operaciones del periodo cuya salida efectiva, debido al retraso, se produzca después de su final.

Introducid variaciones configurables de volumen de vuelos y retrasos por puerta, destino y franja horaria. Podréis establecer una probabilidad diferente de superar el umbral en algunas condiciones para generar un patrón que después deba identificarse mediante las consultas. El generador no asignará por defecto un comportamiento distinto a cada compañía: cualquier diferencia observada deberá analizarse considerando la composición de sus operaciones.

Generad aviones ficticios que puedan aparecer en varias operaciones durante la simulación, incluso en diferentes puertas. La compañía y el modelo se mantendrán constantes para un mismo avión.

Cada nueva operación tendrá un `operation_id` distinto. El número comercial de vuelo, como AS104, podrá repetirse en diferentes días y no servirá para identificar por sí solo una operación. No será necesario simular vuelos de regreso, desplazamientos ni disponibilidad de los aviones. Evitad salidas simultáneas del mismo avión y generad sus operaciones en orden temporal coherente.

Publicad los eventos ordenados por hora efectiva de salida. Cada operación se publicará una sola vez, salvo los reenvíos del modo de prueba. El registro contendrá su hora programada y efectiva; el retraso se calculará después, sin gestionar cambios de estado.

Publicad las salidas en `aeroflow.vuelos` y la configuración en otro topic, por ejemplo, `aeroflow.configuracion`. La configuración también recorrerá NiFi hasta MongoDB.

### Contrato mínimo de una salida

| Campo | Significado |
| --- | --- |
| `event_id` | Identificador único del evento de salida, estable al reenviarlo |
| `schema_version` | Versión del esquema, inicialmente 1 |
| `simulation_id` | Identificador de la ejecución del simulador |
| `scheduled_departure_at` | Fecha y hora simulada de salida programada, almacenada en UTC |
| `actual_departure_at` | Fecha y hora simulada de salida efectiva, almacenada en UTC |
| `emitted_at` | Fecha y hora real de publicación en UTC |
| `terminal_id` | Terminal que publica el registro |
| `gate_id` | Puerta asociada a la operación |
| `aircraft_id` | Identificador ficticio estable del avión |
| `operation_id` | Identificador de la operación concreta de vuelo |
| `flight_number` | Código comercial ficticio, que puede repetirse en distintas operaciones |
| `airline` | Compañía aérea ficticia del avión |
| `aircraft_model` | Modelo del avión, según el catálogo |
| `destination_id` | Destino del catálogo |
| `delay_threshold_minutes` | Umbral del escenario aplicable a esa puerta, en minutos |
| `record_valid` | Validez del registro según el terminal simulado |

En este escenario, cada operación generará un único evento de salida. No se utilizarán matrículas reales ni información personal. Las horas programada y efectiva pertenecen al tiempo simulado; la de publicación pertenece al tiempo real.

### Incidencias controladas

Incluid un modo de prueba capaz de generar mensajes con campos ausentes, JSON incorrecto, registros declarados inválidos y reenvíos del mismo evento. Separad estas incidencias de los datos normales mediante una configuración identificable.

### Apache NiFi: ingestión, transformación y validación

Construid los flujos para consumir salidas y configuración. Interpretad el JSON y validá el esquema antes de insertar los documentos (`ValidateRecord`).

Comprobad al menos:

- Presencia y formato de los identificadores (`ValidateRecord` y `QueryRecord`).
- Versión reconocida del esquema (`QueryRecord`).
- Fechas de salida interpretables y salida efectiva igual o posterior a la programada (`ValidateRecord` y `QueryRecord`).
- Umbral de retraso numérico y positivo (`ValidateRecord` y `QueryRecord`).
- Tipo booleano de `record_valid` (`ValidateRecord`) y separación de los registros según su valor (`QueryRecord`).

Configurad el lector de registros para interpretar las fechas con un formato definido, de forma que puedan compararse como valores temporales.

Corregid únicamente transformaciones justificadas, como normalización de nombres o formatos (`QueryRecord` o `UpdateRecord`). No inventéis valores para completar registros defectuosos.

Los registros que no superen las validaciones o tengan `record_valid = false` se dirigirán a una cola conectada a un Funnel, para permitir su inspección manual. No se insertarán en la colección de salidas válidas ni se incluirán en el análisis de retrasos.

### MongoDB: almacenamiento e índices

Utilizad dos colecciones: `vuelos`, que almacenará los registros de salida que superen las validaciones, y `operativos`, que conservará la configuración de cada simulación.

Estableced un índice único sobre `event_id` para evitar almacenar dos veces la misma salida. Una nueva operación del mismo avión tendrá identificadores de evento y operación diferentes y no se considerará un duplicado.

Proponed índices que faciliten las consultas por simulación, fecha de salida programada, puerta, terminal y avión.

Los registros rechazados permanecerán en la cola conectada al Funnel para su inspección manual y no se almacenarán en MongoDB.

### Dremio: consultas descriptivas dirigidas

Preparad consultas SQL y vistas para responder a las siguientes preguntas. Cada respuesta incluirá consulta, resultado, unidades, filtros y explicación.

Calculad el retraso en minutos como la diferencia entre `actual_departure_at` y `scheduled_departure_at`. Conservad la precisión necesaria para no clasificar incorrectamente operaciones por redondeo. Una operación superará el umbral cuando su retraso sea **estrictamente mayor** que `delay_threshold_minutes`.

#### D1. ¿Cuántas salidas válidas y cuántos aviones distintos se registran por puerta y destino?

Diferenciad operaciones de aviones. Un mismo avión puede aparecer varias veces.

#### D2. ¿Qué puertas presentan mayor porcentaje de vuelos con retraso superior al umbral?

Mostrad salidas válidas, salidas que superan el umbral y su porcentaje. El denominador será el total de salidas válidas de cada grupo.

#### D3. ¿En qué horas y franjas horarias se concentran los retrasos superiores al umbral?

Calculad recuentos y porcentajes por puerta y hora local de salida programada. Utilizad `Europe/Madrid` y documentad la conversión desde UTC. Definid franjas sin solapamiento: madrugada de 00:00 a antes de 06:00, mañana de 06:00 a antes de 12:00, tarde de 12:00 a antes de 18:00 y noche de 18:00 a antes de 24:00.

#### D4. ¿Qué diferencias aparecen entre días laborables y fin de semana?

Comparad salidas, aviones distintos y porcentaje que supera el umbral. Clasificad por fecha local de salida programada. Considerad laborables de lunes a viernes y fin de semana sábado y domingo, sin incorporar festivos.

#### D5. ¿Qué compañías presentan mayor porcentaje de vuelos con retraso superior al umbral?

Mostrad el número de observaciones y aplicad un umbral mínimo de 100 salidas válidas por compañía para la clasificación. Las compañías por debajo del umbral aparecerán en una tabla aparte. Comparad también por puerta o franja para observar posibles diferencias en la composición de la muestra.

#### D6. ¿Cómo varían el retraso medio y la magnitud de la superación del umbral por puerta y destino?

Calculad el retraso medio sobre todas las salidas válidas. Calculad la diferencia media y máxima únicamente sobre las que superan el umbral, restando `delay_threshold_minutes` al retraso calculado. Si no hay superaciones en un grupo, indicadlo explícitamente.

#### D7. ¿Qué aviones registran dos o más operaciones con retraso superior al umbral durante un mismo día?

Identificad avión, fecha local de salida programada, operaciones distintas, número de salidas que superan el umbral y máxima diferencia respecto al umbral. Utilizad `operation_id` para distinguir las operaciones. Un avión con una sola superación en cada uno de varios días no cumple esta condición.

#### D8. ¿Qué modelos presentan mayor porcentaje de vuelos con retraso superior al umbral dentro de cada compañía?

Mostrad salidas válidas, salidas que superan el umbral y porcentaje por compañía y modelo. Para la clasificación, incluid únicamente combinaciones con al menos 100 salidas válidas e indicad cuáles quedan por debajo del umbral.

#### D9. ¿Qué proporción de aviones distintos presenta al menos una operación con retraso superior al umbral?

Calculad el total de aviones distintos y cuántos presentan al menos una superación durante la simulación. Comparad este porcentaje con el porcentaje de salidas que superan el umbral y explicad por qué pueden ser diferentes.

## Reglas analíticas

Todas las métricas se filtrarán por simulación y se calcularán sobre las salidas válidas almacenadas en MongoDB. Utilizad las puertas definidas en la colección `operativos` para mostrar también aquellas con cero salidas. Explicitad los denominadores y evitad dividir entre cero.

Las agrupaciones por hora, día y franja utilizarán la salida programada. La hora efectiva servirá para calcular el retraso y ordenar la evolución de las salidas completadas. Indicad qué fecha utiliza cada visualización.

El retraso mide la diferencia entre salida programada y efectiva. La superación del umbral mide cuánto excede el retraso la referencia del escenario; son indicadores diferentes. Una operación puede tener retraso sin superar el umbral.

Los umbrales son referencias didácticas y no representan criterios legales de compensación ni estándares oficiales de puntualidad.

El porcentaje de salidas que superan el umbral no equivale necesariamente al porcentaje de aviones distintos con alguna superación. El conjunto es sintético y las diferencias por compañía o modelo no prueban causalidad ni describen el funcionamiento real de sus equivalentes.

## Power BI: visualización y analítica descriptiva

Conectad Power BI a las vistas de Dremio mediante DirectQuery. Documentad cómo se refrescan las visualizaciones y demostrad la aparición de nuevos resultados. No se exige actualización automática cada segundo.

Organizad el informe en tres páginas:

| Página | Pregunta | Visualización |
| --- | --- | --- |
| Estado general | ¿Qué volumen se ha observado y qué proporción supera el umbral? | Tarjetas de salidas válidas, aviones distintos, salidas que superan el umbral y porcentaje |
| Estado general | ¿Dónde se concentran los retrasos superiores al umbral? | Esquema de las cinco puertas y barras de porcentaje con recuentos |
| Patrones temporales | ¿Cuándo se registra mayor proporción de superaciones? | Mapa de calor puerta–hora programada y evolución temporal |
| Patrones temporales | ¿Qué cambia entre destinos y tipos de día? | Barras comparativas y filtros |
| Compañías y aviones | ¿Qué diferencias se observan entre compañías y modelos? | Barras de porcentaje con tamaño de muestra y tabla de grupos bajo el umbral |
| Compañías y aviones | ¿Qué aviones acumulan operaciones que superan el umbral durante un mismo día? | Tabla de aviones ficticios, fechas y operaciones |
| Compañías y aviones | ¿Qué diferencia existe entre el porcentaje de salidas que superan el umbral y el de aviones con alguna superación? | Indicadores comparativos de ambos porcentajes |

Incluid filtros de simulación, fecha programada, puerta, destino, compañía y modelo, según corresponda. Mostrad unidades y el alcance de cada indicador. La suma de aviones distintos por puerta no equivale necesariamente al total de aviones distintos del aeropuerto: calculad cada total en su contexto.

El esquema del aeropuerto podrá ser elaborado por el alumnado y no necesita un mapa geográfico. No se exige contratar servicios cartográficos.

## Aplicación web: centro de control

Desarrollad una web que consulte MongoDB mediante una API backend, por ejemplo, FastAPI. El navegador solicitará actualizaciones cada pocos segundos.

Incluirá:

- Selector de simulación.
- Esquema de las cinco puertas y sus terminales asignados.
- Consulta de la configuración almacenada en `operativos`.
- Formulario para preparar la configuración de una nueva simulación.
- Contador de salidas válidas y salidas que superan el umbral por puerta.
- Panel de últimas salidas registradas, ordenadas por `emitted_at`, con número de vuelo, compañía, destino, puerta, hora programada, hora efectiva, retraso y umbral.
- Gráfica de evolución de las salidas basada en `actual_departure_at`.
- Avisos visuales para las operaciones que superen el umbral.
- Fecha real de última actualización y mensaje de error si falla la API.

El backend calculará los retrasos y las superaciones a partir de las fechas y del umbral de cada registro. No será necesario almacenar previamente esos cálculos en MongoDB. Utilizad las mismas reglas y unidades que en Dremio.

El formulario permitirá modificar los umbrales simulados, la asignación de terminales y los parámetros de generación. El backend validará y guardará una nueva configuración, con un `simulation_id` diferente, que leerá el simulador antes de iniciar la siguiente ejecución. Las configuraciones anteriores se conservarán para interpretar sus resultados.

Las credenciales de MongoDB quedarán en el backend. Las consultas y el panel de últimos registros estarán limitados para evitar descargar toda la colección en cada actualización.

Demostrad cómo crecen los contadores mientras NiFi inserta salidas. Identificad los resultados como parciales mientras continúa la ingestión. No se exige detectar desconexiones de terminales ni utilizar mensajes de estado. Iniciar o detener el simulador desde la web y utilizar WebSocket serán ampliaciones voluntarias.

## Pruebas de funcionamiento

Documentad estas pruebas:

1. **Evento válido:** recorre la canalización y aparece en MongoDB, Dremio, la web y Power BI.
2. **Evento repetido:** el reenvío no aumenta el número de salidas almacenadas. Mostrad el comportamiento del flujo ante el conflicto de unicidad.
3. **Mensaje incorrecto:** se dirige a la cola conectada al Funnel y puede inspeccionarse manualmente.
4. **Registro con `record_valid = false`:** se dirige a la cola del Funnel y no aparece en la colección de `vuelos`.
5. **Configuración desde la web:** se guarda una nueva configuración en `operativos` y el simulador la utiliza en la siguiente ejecución, conservando la anterior.
6. **Nuevas salidas:** aparecen al actualizar la web y refrescar las visualizaciones de Power BI.

## Interpretación de resultados

Responded a la pregunta central mediante al menos tres hallazgos respaldados por consultas y visualizaciones. Para cada uno, explicad qué se compara, qué resultado numérico se obtiene y qué limitaciones tiene.

Proponed dos prioridades de seguimiento para el aeropuerto ficticio, por ejemplo, revisar una puerta, un destino o una franja. Justificadlas con porcentajes y tamaños de muestra, no solo con recuentos.

Explicad qué patrones proceden de la configuración del simulador, cuáles aparecen en los resultados y por qué las conclusiones no pueden trasladarse directamente a un aeropuerto real. No se exige optimizar la asignación de puertas ni demostrar el efecto de una redistribución de recursos.

## Entrega del proyecto y documentación requerida

Además de la implementación, se deberá entregar un **vídeo de 10 minutos máximo** mostrando el funcionamiento de la plataforma. También, se desarrollará una **memoria del proyecto** (mínimo 65 páginas y desarrollada con LaTeX) que constará de los siguientes apartados:

1. Introducción
   1. Contextualización
   2. Justificación
   3. Objetivos
   4. Alcance del proyecto
   5. Planificación
2. Marco teórico
3. Fase de análisis
4. Fase de diseño
5. Fase de implementación
6. Fase de pruebas
7. Conclusiones y líneas futuras
8. Bibliografía
9. Diario de trabajo (anexo)
10. Anexos varios

> **La comprobación de plagio supondrá una calificación de 0 puntos.**
>
> Se permite utilizar herramientas de inteligencia artificial únicamente para desarrollar el código del simulador y de la aplicación web, incluido su backend. El alumnado deberá revisar, adaptar y comprobar el código generado, comprender su funcionamiento y explicar su integración con la plataforma. La memoria indicará las herramientas utilizadas y las tareas en las que han intervenido. El análisis de resultados y las conclusiones serán de elaboración propia.

---
