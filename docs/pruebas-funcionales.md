# Pruebas de funcionamiento (1–6)

Documento consolidado que responde a la sección **«Pruebas de funcionamiento»**
del enunciado. Las seis pruebas están ejecutadas contra el despliegue real
(VM `192.168.0.26`: Kafka + NiFi + MongoDB + Dremio + backend web). La
evidencia detallada vive en las guías técnicas; aquí se concentra el resultado
de cada prueba con su verificación y su referencia.

| # | Prueba | Resultado | Evidencia |
|---|---|---|---|
| 1 | Evento válido: canalización completa hasta Power BI | ✅ Superada | `EV-TESTNIFI-0001` visible en Mongo, Dremio, web y Power BI |
| 2 | Evento repetido: reenvío no duplica | ✅ Superada | upsert por `event_id`; 1.007 únicos en 1.007 |
| 3 | Mensaje incorrecto: inspeccionable en la cola del Funnel | ✅ Superada | cola de la conexión `→ DescartesVuelos` listada por API |
| 4 | `record_valid = false` no llega a `vuelos` | ✅ Superada | `invalid` → Funnel; `DEST-UNKNOWN: 0` en Mongo |
| 5 | Configuración desde la web usada en la siguiente ejecución | ✅ Superada | `PRUEBA_01`/`SIM-E376B9557D94`: 393 superaciones frente a 374 |
| 6 | Nuevas salidas visibles web + Power BI, resultados parciales | ✅ Superada | `partial: true`, refresco cada 5 s, franja de aviso |

Estado de los datos al sellar este documento (verificado vía Dremio sobre la
colección `vuelos`):

| Simulación | Salidas | `event_id` únicos |
|---|---|---|
| `SIM-01` (principal) | 1.007 | 1.007 |
| `SIM-E376B9557D94` (`PRUEBA_01`, prueba 5) | 1.007 | 1.007 |
| `SIM-NIFI-TEST` (vuelo manual, prueba 1) | 1 | 1 |
| `SIM-POSTEND` (cruce de fin de periodo) | 101 | 101 |

Las pruebas 1–4 se ejecutaron publicando eventos a mano con un productor
`confluent_kafka` sobre `aeroflow.vuelos` (detalle en
`GUIDE-nifi-flujo-vuelos.md`, §8). Las pruebas 5–6 se ejecutaron desde la
aplicación web (detalle en `GUIDE-centro-control-web.md`, §5–6).

---

## Prueba 1 — Evento válido: recorre la canalización y aparece en todo

**Objetivo.** Publicar un vuelo válido y comprobar su presencia en las cuatro
capas: MongoDB, Dremio, la web y Power BI.

**Procedimiento.** Se publicó `EV-TESTNIFI-0001` (puerta G1, vuelo `AS9001`,
cabecera `flight`) con un productor `confluent_kafka` sobre `aeroflow.vuelos`.
NiFi lo consumió, lo validó contra el esquema Avro, lo clasificó como válido y
`PutMongoRecord` lo insertó con las fechas ya convertidas a BSON `Date`.

**Resultado observado.**

| Capa | Comprobación | Resultado |
|---|---|---|
| MongoDB | `vuelos.findOne({event_id:"EV-TESTNIFI-0001"})` | Documento presente, `simulation_id: SIM-NIFI-TEST` |
| Dremio | `SELECT … FROM V0_salidas WHERE simulation_id='SIM-NIFI-TEST'` | 1 fila, consultable por SQL |
| Web | Selector de simulación → `SIM-NIFI-TEST` | Contadores y tabla muestran el vuelo |
| Power BI | Slicer de simulación → `SIM-NIFI-TEST` | Tarjetas y gráficos muestran 1 salida |

**Verificación viva.** El documento sigue consultable hoy desde Dremio:
`event_id = EV-TESTNIFI-0001`, `gate_id = G1`, `flight_number = AS9001`.
Es el único documento de `SIM-NIFI-TEST` y se conserva a propósito como
evidencia de esta prueba.

---

## Prueba 2 — Evento repetido: el reenvío no aumenta las salidas

**Objetivo.** Reenviar el mismo evento y comprobar que el número de salidas
almacenadas no crece, mostrando cómo resuelve el flujo el conflicto de
unicidad.

**Procedimiento.** Se reenvió `EV-TESTNIFI-0001` idéntico (mismo `event_id`).

**Resultado observado.** El conteo de `vuelos` no cambia. La unicidad la
resuelve `PutMongoRecord` con **upsert** (reemplazo por `event_id`), de modo
que el reenvío actualiza en lugar de insertar. Comprobación agregada tras la
simulación completa: **1.007 documentos `SIM-01` y 1.007 `event_id`
distintos** (0 duplicados por agregación):

```javascript
db.vuelos.aggregate([
  {$match: {simulation_id: "SIM-01"}},
  {$group: {_id: "$event_id", n: {$sum: 1}}},
  {$match: {n: {$gt: 1}}}
])  // → vacío
```

**Corolario de diseño.** El `event_id` es determinista (se deriva de la
configuración y la semilla), y `vuelos` tiene índice único sobre él. Repetir
una simulación ya cargada, por web o por Kafka, reproduce el mismo
comportamiento: conflicto de unicidad resuelto, sin filas nuevas. Es el
mismo mecanismo que protege a la prueba 5 cuando se reejecuta.

**Limitación conocida.** El upsert *reemplaza* el documento: si el reenvío
llegara con datos distintos, la última versión ganaría. El enunciado solo
exige no duplicar, que es lo comprobado.

---

## Prueba 3 — Mensaje incorrecto: inspeccionable en la cola del Funnel

**Objetivo.** Enviar un mensaje incorrecto a la cola conectada al Funnel y
poder inspeccionarlo manualmente.

**Procedimiento.** Se publicaron tres familias de mensajes incorrectos por la
cola `aeroflow.vuelos`:

- JSON malformado → `ValidateEsquemaVuelo` falla el parseo → relación `failure`.
- Mensaje de la cola `/test-events` (cabecera `test`, ilegible a propósito)
  → relación `prueba`.
- Campos ausentes o con tipos inválidos → relación `invalid`.

**Resultado observado.** Los tres caminos acaban en `DescartesVuelos` (Funnel),
que acumula los FlowFiles con sus atributos de diagnóstico
(`validation.details` lleva el motivo exacto del rechazo).

**Cómo se inspecciona (manualmente).** El Funnel no expone cola propia, pero
la **conexión que llega a él** sí:

```bash
# 1. pedir el listado de la cola (por API, con token de NiFi)
curl -sk -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://nifi.monolith.dynamic-dns.net/nifi-api/flowfile-queues/$CONN_ID/listing-requests \
  -d '{"drop":false}'
# 2. leer el resultado con el id de la peticion
curl -sk -H "Authorization: Bearer $TOKEN" \
  .../flowfile-queues/$CONN_ID/listing-requests/$REQUEST_ID
```

En la UI: clic derecho sobre la conexión → **List queue**, o sobre el
procesador → **Data provenance**. En el listado se ven los FlowFiles
descartados con su contenido y el motivo.

---

## Prueba 4 — `record_valid = false`: a la cola del Funnel, nunca a `vuelos`

**Objetivo.** Un registro marcado como inválido debe dirigirse a la cola del
Funnel y no aparecer en la colección `vuelos`.

**Procedimiento y resultado.** `ClasificarVuelo` (QueryRecord) enruta a
`invalid` todo lo que llega con `record_valid = false`. En la campaña de
pruebas se confirmó con los casos defectuosos reales del generador (5 % de
1.060 operaciones = **53 rechazos**, 5,0 %):

| Rechazo | Cantidad | Puerta de salida |
|---|---|---|
| Campos ausentes / tipos inválidos | 14 | `ValidarEsquemaVuelo` → `invalid` |
| Umbral no positivo (`delay_threshold_minutes: 0`) | 13 | `ClasificarVuelo` → `invalid` |
| Salida efectiva anterior a la programada | 13 | `ClasificarVuelo` → `invalid` |
| Destino fuera del catálogo (`DEST-UNKNOWN`) | 13 | `ClasificarVuelo` → `invalid` |

Cada caso completo con `record_valid = false` fue a `invalidos` → Funnel.

**Verificación en la colección.** Ningún registro defectuoso llegó a `vuelos`:

```javascript
print("SIM-01:", v.countDocuments({simulation_id: "SIM-01"}));                       // 1007
print("DEST-UNKNOWN:", v.countDocuments({simulation_id: "SIM-01",
                                        destination_id: "DEST-UNKNOWN"}));           // 0
```

Además, Dremio confirma hoy que los 1.007 documentos de `SIM-01` son todos
válidos y únicos.

---

## Prueba 5 — Configuración desde la web: se guarda, se usa y se conserva

**Objetivo.** Guardar una configuración nueva en `operativos` desde la web,
que el simulador la use en la siguiente ejecución y que la anterior se
consERVE.

**Procedimiento.** Desde el cajón «Nueva simulación» de la web se creó
**`PRUEBA_01`** partiendo de `SIM-01` con dos cambios: umbral de G1 de 15 a
**20 min**, e intercambio de terminales G4↔G5. El backend la guardó en
`operativos` con un `simulation_id` nuevo (`SIM-E376B9557D94`) y **no arrancó
nada por su cuenta**: el formulario solo prepara la siguiente ejecución.

**Resultado observado.** Al ejecutar la siguiente simulación, el generador
cargó `PRUEBA_01` de `operativos` y produjo:

| Parámetro | `SIM-01` | `PRUEBA_01` |
|---|---|---|
| Umbral de G1 | 15 min | 20 min |
| Terminales de G4/G5 | T4 / T5 | **T5 / T4** |
| Salidas válidas | 1.007 | 1.007 |
| Superaciones | 374 (37,14 %) | **393 (39,03 %)** |
| G1: superaciones con el umbral subido | 93 | **87** |
| G4 | 206 / 128 | 205 / 120 (misma conducta) |

Lectura: subir el umbral de G1 (15→20) hace que **baje** sus superaciones
(93→87) sin cambiar las demás puertas; el intercambio de terminales se refleja
en la vista (`G4` figura en `T5`, `G5` en `T4`). Y `SIM-01` permanece intacta
(1.007 / 374) en el selector: **la configuración anterior se conserva**.

Evidencia visual: `docs/capturas-web/prueba-funcional-5.png`.

---

## Prueba 6 — Nuevas salidas: visibles en web y Power BI durante la ingesta

**Objetivo.** Las salidas nuevas aparecen al actualizar la web y refrescar
Power BI, identificando los resultados como **parciales** mientras NiFi sigue
insertando.

**Procedimiento.** Arrancar `SIM-01` desde el controlador de la web y observar
ambos clientes durante la ingesta.

**Resultado observado.**

1. Mientras dura la ingesta, la API devuelve `partial: true` y la web muestra
   la franja **«Resultados parciales: NiFi sigue insertando. Los contadores
   pueden crecer.»**
2. La web se refresca sola cada 5 s: salidas válidas, superaciones y aviones
   distintos crecen a medida que NiFi inserta; la tabla reordena por
   `emitted_at` y las salidas nuevas aparecen arriba.
3. Al terminar, `partial` pasa a `false` y la franja desaparece.
4. Si la simulación en marcha no es la que se está viendo, la franja lo dice
   explícitamente («estás viendo …; sus datos no son parciales»).
5. En **Power BI** (DirectQuery), el botón **Actualizar** vuelve a consultar
   Dremio y las tarjetas y gráficos incorporan las salidas nuevas al momento.

**Cifras de la ejecución de referencia** (de 0 a final, observadas en la web
mientras crecían): 0 → 1.007 salidas; 53 publicaciones defectuosas quedaron
fuera. Los contadores finales de la web coinciden con MongoDB porque el
backend recalcula en cada consulta a partir de las fechas y el umbral.

---

## Resumen por objetivo del enunciado

| Objetivo del enunciado | Dónde queda demostrado |
|---|---|
| «recorre la canalización y aparece en MongoDB, Dremio, la web y Power BI» | Prueba 1 (las cuatro capas, con documento vivo hoy) |
| «el reenvío no aumenta el número de salidas… conflicto de unicidad» | Prueba 2 (upsert por `event_id`, 0 duplicados) |
| «se dirige a la cola conectada al Funnel y puede inspeccionarse» | Prueba 3 (listing por API y UI) |
| «se dirige a la cola del Funnel y no aparece en `vuelos`» | Prueba 4 (53 rechazos, 0 en la colección) |
| «se guarda en `operativos`… la utiliza en la siguiente ejecución, conservando la anterior» | Prueba 5 (PRUEBA_01 usada; SIM-01 intacta) |
| «aparecen al actualizar la web y refrescar Power BI» + resultados parciales | Prueba 6 (`partial: true`, refresco 5 s) |
