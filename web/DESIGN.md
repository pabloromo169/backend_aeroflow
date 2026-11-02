# AeroFlow · Diseño del frontend

**Estado:** diseño acordado. Fase 1 (contrato backend) implementada; fases 2–9 pendientes.
**Objetivo:** cerrar la arquitectura, los estados, el contrato con la API y el plan de
implementación antes de escribir la web.

---

## 1. Objetivo y alcance

La web es el **centro de control** de AeroFlow y responde a la segunda pregunta del
enunciado:

> ¿Cómo comprobamos que los cinco terminales están enviando datos y que las salidas se
> están incorporando al almacén?

Debe permitir:

- elegir una simulación;
- ver el esquema de las cinco puertas y sus terminales;
- consultar la configuración guardada;
- crear una configuración nueva;
- ver contadores globales y por puerta;
- ver la evolución de las salidas;
- ver las últimas salidas con su retraso y umbral;
- distinguir resultados parciales mientras NiFi sigue insertando;
- saber cuándo se actualizó por última vez y si la API falla.

### 1.1. Dentro del alcance

- Una sola página de monitorización.
- Un cajón lateral para configuración y alta de simulación.
- Consulta y escritura contra la API existente.
- Arranque y parada de simulaciones (ampliación voluntaria).
- Despliegue con systemd y Traefik.
- Diseño adaptado de escritorio a tablet y móvil.

### 1.2. Fuera del alcance

- Autenticación propia dentro de la app; se resuelve con basic auth en Traefik.
- WebSockets; el enunciado no los exige.
- Edición del catálogo de destinos, compañías, modelos o flota.
- Repetir el análisis de Power BI dentro de la web.
- Detección de terminales desconectados.
- Tests de navegador automatizados.

---

## 2. Decisiones cerradas

| Tema | Decisión |
|---|---|
| Stack | HTML + CSS + JavaScript nativo con módulos ES, sin build |
| Servidor | FastAPI sirve `web/` con `StaticFiles`; API bajo `/api/*` |
| Navegación | Una página + cajón lateral derecho; `?panel=config` lo abre |
| Tema | Claro operativo: cabecera azul marino, tarjetas blancas, avisos ámbar/rojo |
| Tipografía | Inter desde Google Fonts con fallback al sistema |
| Formulario | Campos estructurados + bloque avanzado plegable + JSON de solo lectura |
| Destinos | Catálogo fijo `DEST-01`…`DEST-04`, siempre en solo lectura |
| Terminales | Reasignables entre puertas, manteniendo biyección T1–T5 |
| Control | Arrancar y parar simulación desde la web, con confirmación |
| Polling | Cada 5 s; pausa con `document.hidden`; refresco inmediato tras acciones |
| Selector inicial | Simulación activa; si no, `SIM-01`; estado en la URL |
| Selector | Solo configuraciones de `operativos` (no simulaciones huérfanas) |
| Puertas | Muelle horizontal de cinco tarjetas clicables |
| Gráfica | Barras SVG apiladas, selector hora/día, base UTC |
| Tabla | 20 filas por página, paginación anterior/siguiente, filtros de página |
| Errores API | Banner persistente + datos anteriores atenuados + frescura por bloque |
| Parcialidad | Etiqueta «Resultados parciales» + progreso `publicados/total` |
| Totales | Ampliar `summary` con `totals` y `distinct_aircraft` |
| Timeline | Ampliar cada bucket con `above_threshold` |
| Fechas | Mostrar UTC en toda la interfaz, formato `YYYY-MM-DD HH:MM UTC` |
| Accesibilidad | AA básico manual, teclado, `aria-live`, foco visible |
| Seguridad | Basic auth en Traefik, CSP y cabeceras desde FastAPI |
| Despliegue | `aeroflow-backend.service` + Traefik `aeroflow.monolith.dynamic-dns.net` |
| Idioma | Español; identificadores técnicos en inglés |

---

## 3. Principios de diseño

1. **El estado del sistema se entiende en un vistazo.** Cabecera con simulación, estado
   y última actualización; después métricas, puertas, evolución y detalle.
2. **Nunca ocultar el esquema del aeropuerto.** Aunque no haya datos, las cinco puertas
   siguen visibles con sus terminales y umbrales.
3. **El color no es la única señal.** Toda superación lleva texto o icono además del
   color.
4. **Los datos obsoletos se ven obsoletos.** Si falla la API, se conserva lo último
   bueno pero atenuado y con la hora del último éxito.
5. **Una acción, una confirmación.** Crear no arranca; arrancar y parar piden
   confirmación.
6. **Consultas acotadas.** La web nunca descarga la colección completa: 20 filas por
   página y agregados calculados en el backend.

---

## 4. Arquitectura de información

```text
/  (centro de control)
│
├── Cabecera fija
│   ├── Título
│   ├── Selector de simulación
│   ├── Pill de estado
│   ├── Última actualización UTC
│   └── Acciones: Actualizar · Configurar · Arrancar/Parar
│
├── Banner de conexión / parcialidad
│
├── Contadores globales (4 tarjetas)
│
├── Muelle de puertas (5 tarjetas)
│
├── Evolución (barras apiladas)
│
├── Últimas salidas (tabla paginada + filtros de página)
│
└── Cajón de configuración
    ├── Pestaña «Configuración actual»
    └── Pestaña «Nueva simulación»
```

### 4.1. Estado en la URL

```text
/?sim=SIM-01&panel=monitor&page=1&interval=hour
```

- `sim`: simulación seleccionada.
- `panel`: `monitor` o `config`.
- `page`: página de la tabla; se omite si es 1.
- `interval`: `hour` o `day`.

Reglas:

- `history.replaceState` durante el polling y cambios que no son navegación.
- `history.pushState` al cambiar de simulación, abrir/cerrar el cajón o cambiar de
  página.
- Los filtros de tabla **no** se guardan en la URL en esta versión.
- Si `sim` no existe, se cae a la activa, luego a `SIM-01`, luego a la primera
  configuración disponible.

---

## 5. Wireframe de escritorio

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ AeroFlow · Centro de control                                                │
│ [SIM-01 ▾]  ● Parcial · 640/1060          Última: 2026-11-02 19:58:12 UTC   │
│                                      [Actualizar] [Configurar] [Parar]      │
├──────────────────────────────────────────────────────────────────────────────┤
│ ⚠ Resultados parciales: NiFi sigue insertando. Los contadores pueden crecer.│
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│ │ Salidas      │ │ Superan      │ │ % superior   │ │ Aviones      │         │
│ │ válidas      │ │ umbral       │ │ al umbral    │ │ distintos    │         │
│ │ 1.007        │ │ 374          │ │ 37,14 %      │ │ 50           │         │
│ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘         │
├──────────────────────────────────────────────────────────────────────────────┤
│ Muelle de puertas                                                           │
│ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐  │
│ │ G1 · T1    │ │ G2 · T2    │ │ G3 · T3    │ │ G4 · T4    │ │ G5 · T5    │  │
│ │ Umbral 15  │ │ Umbral 15  │ │ Umbral 15  │ │ Umbral 20  │ │ Umbral 15  │  │
│ │ 257 salidas│ │ 183        │ │ 224        │ │ 206        │ │ 137        │  │
│ │ 87 · 33,9 %│ │ 61 · 33,3 %│ │ 82 · 36,6 %│ │ 90 · 43,7 %│ │ 54 · 39,4 %│  │
│ │ ▓▓▓░░░░░░  │ │ ▓▓▓░░░░░░  │ │ ▓▓▓▓░░░░░  │ │ ▓▓▓▓░░░░░  │ │ ▓▓▓▓░░░░░  │  │
│ └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Evolución por hora efectiva (UTC)                              [Hora ▾]     │
│  ▁  ▂  ▃  ▅  ▇  █  ▆  ▄  ▃  ▂  ▁                                            │
│  █ = salidas bajo umbral   ▓ = salidas que superan el umbral                │
│  2026-10-05 00:00 UTC … 2026-10-11 23:00 UTC                                │
├──────────────────────────────────────────────────────────────────────────────┤
│ Últimas salidas (total 1.007)                                               │
│ [Puerta ▾] [Compañía ▾] [Destino ▾] [ ] Solo superaciones  [Limpiar]        │
│ ┌──────┬──────────┬─────────┬────────┬────────────┬────────────┬──────────┐ │
│ │Vuelo │Compañía  │Destino  │Puerta  │Programada  │Efectiva    │Retraso   │ │
│ ├──────┼──────────┼─────────┼────────┼────────────┼────────────┼──────────┤ │
│ │A01143│Aero01    │DEST-03  │G1 · T1 │2026-10-11  │2026-10-11  │  24 min  │ │
│ │      │          │         │        │13:56 UTC   │14:20 UTC   │ ⚠ Supera │ │
│ └──────┴──────────┴─────────┴────────┴────────────┴────────────┴──────────┘ │
│ Página 1 de 51                                     [Anterior] [Siguiente]   │
└──────────────────────────────────────────────────────────────────────────────┘

                                      ┌──────────────────────────────────────┐
                                      │ Configuración                   [×] │
                                      │ [Actual] [Nueva simulación]         │
                                      │                                      │
                                      │ Nombre …                            │
                                      │ Inicio (UTC) …                      │
                                      │ Días …  Operaciones …               │
                                      │ …                                   │
                                      │                                      │
                                      │ [Cancelar]                [Guardar] │
                                      └──────────────────────────────────────┘
```

---

## 6. Wireframe móvil

```text
┌──────────────────────────────┐
│ AeroFlow · Centro de control│
│ [SIM-01 ▾]  ● Parcial       │
│ Última: 19:58:12 UTC        │
│ [Actualizar] [Configurar]   │
│ [Arrancar] / [Parar]        │
├──────────────────────────────┤
│ ⚠ Resultados parciales      │
├──────────────────────────────┤
│ ┌────────────┐ ┌───────────┐ │
│ │ Salidas    │ │ Superan   │ │
│ └────────────┘ └───────────┘ │
│ ┌────────────┐ ┌───────────┐ │
│ │ %          │ │ Aviones   │ │
│ └────────────┘ └───────────┘ │
├──────────────────────────────┤
│ G1 · T1 · Umbral 15         │
│ 257 · 87 · 33,9 %           │
│ ▓▓▓░░░░░░                   │
├──────────────────────────────┤
│ (repite G2 … G5)             │
├──────────────────────────────┤
│ Evolución        [Hora ▾]   │
│ ▁ ▂ ▃ ▅ ▇ █ ▆ ▄ ▃          │
├──────────────────────────────┤
│ Últimas salidas             │
│ [filtros en una línea]      │
│ ┌──────────────────────────┐ │
│ │ A01143 · Aero01          │ │
│ │ G1 · DEST-03 · 24 min    │ │
│ │ ⚠ Supera umbral          │ │
│ └──────────────────────────┘ │
│ Página 1 de 51              │
│ [Anterior] [Siguiente]      │
└──────────────────────────────┘

Cajón de configuración: ocupa el 100 % del ancho.
La tabla pasa a scroll horizontal; el muelle a una columna.
```

---

## 7. Estructura de componentes

```text
App
├── SkipLink
├── Header
│   ├── Brand
│   ├── SimulationSelect
│   ├── StatusPill
│   ├── LastUpdate
│   └── HeaderActions
│       ├── RefreshButton
│       ├── ConfigButton
│       └── StartStopButton
├── ConnectionBanner
├── PartialBanner
├── GlobalMetrics
│   └── MetricCard × 4
├── GatePier
│   └── GateCard × 5
├── EvolutionPanel
│   ├── IntervalSwitch
│   ├── StackedBarChart (SVG)
│   └── Legend
├── DeparturesPanel
│   ├── TableFilters
│   ├── DeparturesTable
│   └── Pagination
├── ConfigDrawer
│   ├── DrawerHeader
│   ├── DrawerTabs
│   ├── CurrentConfigPanel
│   ├── NewConfigForm
│   │   ├── GeneralFields
│   │   ├── GateThresholds
│   │   ├── TerminalAssignments
│   │   ├── GenerationProfiles
│   │   └── AdvancedJsonPreview
│   └── DrawerFooter
├── ConfirmDialog
└── ToastRegion
```

### 7.1. Módulos JavaScript

| Archivo | Responsabilidad |
|---|---|
| `main.js` | Arranque, cableado de eventos, ciclo de vida |
| `api.js` | `fetch` con timeout, errores normalizados y JSON |
| `state.js` | Estado en memoria, selección, filtros y derivados |
| `polling.js` | Temporizador de 5 s, pausa por visibilidad y refresco forzado |
| `render.js` | Render de cabecera, métricas, puertas y banners |
| `table.js` | Tabla, paginación y filtros de página |
| `charts.js` | SVG de barras apiladas y ejes |
| `config-form.js` | Cajón, formulario, validación y JSON de vista previa |
| `dialogs.js` | Confirmaciones, foco atrapado y toasts |
| `format.js` | Fechas UTC, minutos, porcentajes y textos |

Sin dependencias externas de JavaScript. Inter se carga desde Google Fonts.

---

## 8. Lenguaje visual

### 8.1. Paleta

```css
:root {
  --af-navy: #12324a;
  --af-navy-strong: #0d2638;
  --af-bg: #f4f6f8;
  --af-surface: #ffffff;
  --af-ink: #17212b;
  --af-muted: #5b6b7a;
  --af-border: #d7dee5;
  --af-focus: #1d4ed8;
  --af-live: #166534;
  --af-live-soft: #dcfce7;
  --af-warn: #b45309;
  --af-warn-soft: #fef3c7;
  --af-danger: #b91c1c;
  --af-danger-soft: #fee2e2;
  --af-info-soft: #e0f2fe;
}
```

La cabecera usa `--af-navy` con texto blanco. El contenido va sobre `--af-bg` y las
tarjetas sobre `--af-surface`. Los estados usan siempre icono y texto:

- **En directo:** verde `--af-live`, icono de punto.
- **Parcial:** ámbar `--af-warn`, icono de reloj.
- **Sin conexión:** rojo `--af-danger`, icono de alerta.
- **Supera umbral:** fondo `--af-warn-soft`, borde ámbar y etiqueta «⚠ Supera».
- **Bajo umbral:** sin color de alarma, etiqueta «Dentro del umbral».

### 8.2. Tipografía

- Familia: `Inter`, con fallback `system-ui, -apple-system, "Segoe UI", Roboto,
  sans-serif`.
- Carga: Google Fonts con `display=swap`.
- Tamaños:
  - Título de página: 24 px / 1.2.
  - Título de bloque: 16 px / 1.3, semibold.
  - Cuerpo y tablas: 14 px / 1.45.
  - Metadatos y ayudas: 12 px / 1.4.
  - Cifras grandes de tarjeta: 30 px / 1.1, tabular.
- Los números usan `font-variant-numeric: tabular-nums`.

### 8.3. Espaciado y forma

- Escala de 4 px: 4, 8, 12, 16, 24, 32, 48.
- Radio de tarjeta: 12 px; botones: 8 px; pills: 999 px.
- Sombra suave solo en cabecera fija y cajón; el resto usa borde de 1 px.
- Ancho máximo del contenido: 1440 px.
- Márgenes laterales: 24 px en escritorio, 16 px en tablet, 12 px en móvil.

### 8.4. Rejilla

- Métricas: 4 columnas → 2 → 2 → 1.
- Puertas: 5 columnas → 3 → 2 → 1.
- Gráfica y tabla: ancho completo.
- Breakpoints: 1200 px, 1024 px, 720 px, 480 px.
- La tabla conserva su estructura y hace scroll horizontal en pantallas pequeñas.

### 8.5. CSS

- BEM ligero con prefijo `af-`: `af-card`, `af-card__title`,
  `af-card--alert`.
- Variables CSS para todos los tokens.
- Sin utilidades tipo Tailwind ni estilos inline, salvo valores calculados en SVG.
- `prefers-reduced-motion` desactiva transiciones no esenciales.

---

## 9. Cabecera

Contenido, de izquierda a derecha:

1. **Título:** `AeroFlow · Centro de control`.
2. **Selector de simulación:** `SIM-01` + nombre, con las configuraciones de
   `operativos`.
3. **Pill de estado:** `En directo`, `Parcial` o `Sin conexión`.
4. **Última actualización:** `Última: YYYY-MM-DD HH:MM:SS UTC`.
5. **Acciones:**
   - `Actualizar`: refresco manual inmediato.
   - `Configurar`: abre el cajón en la pestaña actual.
   - `Arrancar`: visible si no hay simulación activa.
   - `Parar`: visible solo si el estado es `running` o `stopping`.

En móvil, el título y el selector van en la primera línea; el estado y la última
actualización en la segunda; las acciones se reparten en dos filas.

### 9.1. Selector

- Orden: `SIM-01` primero, después el resto por ID.
- Texto: `SIM-01 · Aeropuerto simulado Bahía de Cádiz`.
- Metadatos: salidas almacenadas y última emisión.
- No incluye simulaciones sin configuración, como `SIM-NIFI-TEST`.
- Incluye `SIM-VALID-API` y `SIM-FINAL` aunque no tengan salidas; el panel mostrará el
  estado vacío.
- Incluye `SIM-POSTEND`; es útil para demostrar avisos de umbral y resultados al 100 %.

### 9.2. Regla de selección inicial

1. Si `?sim=` existe y la configuración existe, se usa.
2. Si hay una simulación en estado `running` o `stopping`, se usa esa.
3. Si no, `SIM-01`.
4. Si no existe, la primera configuración disponible.
5. Si no hay ninguna, se muestra un estado de error con enlace a Configurar.

---

## 10. Contadores globales

Cuatro tarjetas, siempre con el alcance visible:

| Tarjeta | Dato | Nota |
|---|---|---|
| Salidas válidas | `totals.valid_departures` | Registros con `record_valid=true` |
| Superan umbral | `totals.above_threshold` | Retraso estrictamente mayor que el umbral |
| Porcentaje | `totals.above_threshold_percentage` | `superan / válidas × 100`, un decimal |
| Aviones distintos | `totals.distinct_aircraft` | Global; no es la suma de aviones por puerta |

- El porcentaje se muestra con coma decimal en español: `37,14 %`.
- Si no hay salidas, todas las tarjetas muestran `0` y el porcentaje `—`, no `0 %`
  ambiguo.
- La tarjeta de aviones lleva una nota: «Un avión puede operar en varias puertas».
- Los totales se calculan en el backend, no sumando las cinco puertas en el cliente.

---

## 11. Muelle de puertas

Cinco tarjetas en fila. Cada tarjeta muestra:

- `G1` … `G5`;
- nombre de la puerta;
- terminal asignado (`T1` … `T5`);
- umbral en minutos;
- salidas válidas;
- superaciones;
- porcentaje con un decimal;
- barra local de proporción.

La barra se escala solo contra el total de esa misma puerta; no se comparan alturas
entre puertas, para no confundir volumen con porcentaje.

### 11.1. Interacción

- Toda la tarjeta es clicable y accesible por teclado.
- Al hacer clic: fija el filtro de página `Puerta = Gx`, hace scroll suave a la tabla y
  muestra un chip `Puerta Gx · Quitar filtro`.
- No cambia la simulación ni recarga los datos.
- Si la puerta no tiene salidas, muestra `0` y `—` en el porcentaje, pero sigue
  visible.
- `aria-label`: «Puerta G1, terminal T1, umbral 15 minutos, 257 salidas, 87
  superaciones, 33,9 por ciento».

---

## 12. Evolución

- Gráfica SVG de barras apiladas.
- Eje X: buckets de hora o día en UTC.
- Eje Y: número de salidas.
- Cada barra tiene dos segmentos:
  - base: salidas bajo umbral;
  - superior: salidas que superan el umbral.
- Leyenda textual: `Bajo umbral` y `Supera umbral`.
- Selector `Hora` / `Día`; por defecto `Hora`.
- Etiqueta del eje: `Hora efectiva (UTC)`.
- Si hay muchas horas, se muestran etiquetas cada N buckets para evitar solapamiento.
- Tooltip nativo con `title` o panel al pasar el ratón: fecha, salidas totales,
  superaciones y porcentaje.
- Sin datos: se dibuja el eje y un mensaje «Sin salidas en este intervalo».
- La gráfica no usa librerías externas; se genera con `createElementNS`.

### 12.1. Cambio de intervalo

- `hour`: resolución horaria, útil para el detalle de una jornada.
- `day`: resolución diaria, útil para ver los siete días.
- El intervalo se refleja en `?interval=`.
- Al cambiar, se conserva la simulación y la página de la tabla.

---

## 13. Últimas salidas

### 13.1. Columnas

| Columna | Contenido |
|---|---|
| Vuelo | `flight_number` |
| Compañía | `airline` |
| Destino | `destination_id` |
| Puerta | `gate_id · terminal_id` |
| Programada | `YYYY-MM-DD HH:MM UTC` |
| Efectiva | `YYYY-MM-DD HH:MM UTC` |
| Retraso | minutos, con una decimal si procede |
| Umbral | minutos |
| Estado | «⚠ Supera» o «Dentro del umbral» |

Se muestran solo salidas con `record_valid=true`, ya filtradas por el backend. Los
registros rechazados están en el Funnel de NiFi y no forman parte de la web.

### 13.2. Paginación

- 20 filas por página.
- Controles: `Anterior`, `Página X de Y`, `Siguiente`.
- Se deshabilitan en los extremos.
- La página se refleja en `?page=`.
- El total de filas se muestra en el título: `Últimas salidas (total 1.007)`.
- Si se cambia de simulación, se vuelve a la página 1.

### 13.3. Filtros de página

Filtros en memoria, aplicados **solo a las 20 filas cargadas**:

- Puerta.
- Compañía.
- Destino.
- Solo superaciones (checkbox).

Reglas:

- Las opciones se derivan de la página actual.
- Se muestra la etiqueta «Filtros sobre esta página».
- Si no hay coincidencias: «Sin filas con estos filtros» + botón `Limpiar filtros`.
- El clic en una puerta fija el filtro de puerta.
- No se persisten en la URL ni en `localStorage` en esta versión.
- El filtro de puerta se refleja en un chip junto al título de la tabla.

### 13.4. Avisos

- Fila con superación: fondo `--af-warn-soft`, borde izquierdo ámbar y etiqueta
  «⚠ Supera».
- Fila normal: sin color de alarma.
- El retraso se muestra en minutos; si es negativo por un registro anómalo, se marca
  como error de dato y no se oculta.
- La tabla tiene `caption` accesible y `scope="col"` en las cabeceras.

---

## 14. Cajón de configuración

### 14.1. Contenedor

- Cajón lateral derecho de 520 px en escritorio; 100 % en móvil.
- Cabecera fija con título y botón de cierre.
- Cuerpo con scroll independiente.
- Pie fijo con `Cancelar` y `Guardar`.
- Fondo oscurecido y clic fuera para cerrar.
- `Escape` cierra.
- Si hay cambios sin guardar, se pide confirmación antes de cerrar.
- Foco atrapado dentro del cajón; al cerrar, vuelve al botón que lo abrió.

### 14.2. Pestañas

1. **Configuración actual** (solo lectura).
2. **Nueva simulación** (formulario).

La pestaña activa se conserva mientras el cajón está abierto, pero no en la URL.

#### Configuración actual

- Resumen legible por secciones:
  - identidad: ID, nombre, zona horaria, inicio, días;
  - generación: operaciones, intervalo, semilla, tasa de defectos;
  - puertas: ID, nombre, terminal, umbral;
  - destinos: ID y nombre;
  - compañías, modelos y flota;
  - perfiles de generación.
- Metadatos de la simulación: salidas almacenadas, última emisión y estado.
- `<details>` con el JSON completo y botón `Copiar`.
- Botón `Duplicar como nueva`: cambia a la pestaña de alta con los campos
  precargados y nombre `Copia de …`.

#### Nueva simulación

- Parte de la configuración seleccionada.
- El ID y la semilla los asigna el backend; el formulario no los inventa.
- No arranca la simulación al guardar.

### 14.3. Campos editables

**Identidad y generación**

- `name`: texto obligatorio.
- `simulation_start`: `datetime-local` etiquetado `UTC`.
- `simulation_days`: entero 7–31.
- `total_operations`: entero 100–100000.
- `publish_interval_ms`: entero 0–60000.
- `random_seed`: entero ≥ 0, heredado, con botón `Generar nueva`; si se vacía, se
  envía `null` y el backend asigna una.

**Puertas**

- Umbral por puerta: entero ≥ 1, unidad `min`.
- Terminal por puerta: selector `T1`–`T5`.

**Perfiles de generación**

- `base_delay_probability`: 0–1, paso 0,01.
- `max_delay_minutes_beyond_threshold`: entero 1–1440.
- Tablas clave/valor para:
  - volumen por puerta (`G1`–`G5`);
  - volumen por destino (`DEST-01`–`DEST-04`);
  - volumen por franja (`night`, `morning`, `afternoon`, `evening`);
  - multiplicador de retraso por puerta;
  - multiplicador de retraso por destino;
  - multiplicador de retraso por franja.

Todas las claves fijas deben estar presentes. Los pesos de volumen son positivos; los
multiplicadores están entre 0 y 4. Las tablas muestran la unidad o el rango en la ayuda.

### 14.4. Campos de solo lectura

- `timezone`: `Europe/Madrid`.
- `defect_rate`: `0.05`.
- `destinations`: `DEST-01`…`DEST-04` con sus nombres.
- `airlines`, `aircraft_models`, `aircraft`.
- IDs de puerta `G1`–`G5`.
- `simulation_id` y `random_seed` cuando los asigna el backend.

El catálogo de destinos es fijo y coincide con la lista de `ClasificarVuelo` en NiFi.
La API rechaza cualquier configuración con otros destinos.

### 14.5. Terminales

- Cada puerta tiene un selector con los cinco terminales.
- Al elegir un terminal ya usado, se intercambia automáticamente con la puerta que lo
  tenía.
- Se muestra un aviso breve: «T2 asignado a G2; G3 recibe T3».
- Nunca se permite guardar dos puertas con el mismo terminal.
- La asignación uno a uno se mantiene siempre.

### 14.6. Bloque avanzado

- Plegado por defecto.
- Resumen de una línea: «Perfiles: 5 puertas · 4 destinos · 4 franjas».
- Dentro, las tablas de pesos y multiplicadores.
- Al final, un `<pre>` de solo lectura con el JSON resultante y botón `Copiar`.
- El JSON no se edita a mano ni se envía como texto; se reconstruye desde los campos.
- El bloque se puede abrir sin perder los valores ya introducidos.

### 14.7. Validación

**En navegador**

- Campos obligatorios.
- Rangos numéricos.
- Fechas válidas.
- Terminales únicos.
- Pesos positivos y multiplicadores en rango.
- Al menos una clave por tabla.
- Nada se envía si falla la validación básica.

**En servidor**

- El backend valida de nuevo con Pydantic.
- Un `422` se mapea a los campos mediante `loc` cuando la ruta es reconocible.
- Los errores generales se muestran en la cabecera del cajón.
- Los valores introducidos se conservan.
- Un `409` al crear se muestra como conflicto de ID.
- Un `503` se muestra como «MongoDB no disponible; reintenta».

### 14.8. Guardar

1. Se pulsa `Guardar`.
2. Se valida en cliente.
3. Se envía `POST /api/configurations`.
4. Si `201`:
   - se cierra el cajón;
   - se selecciona la nueva simulación;
   - se refresca el panel;
   - toast: «Configuración SIM-… guardada. Pulsa Arrancar para ejecutarla».
5. No se arranca automáticamente.
6. Si falla, el cajón permanece abierto con el error mapeado.

---

## 15. Controles de simulación

### 15.1. Arrancar

- Botón visible si no hay una simulación en curso.
- Modal de confirmación:
  - ID y nombre;
  - total de operaciones;
  - aviso: «Se publicará la configuración y comenzará la simulación».
- Si el backend responde `409` porque ya hay una activa, se muestra:
  «Ya hay una simulación en curso: SIM-…».
- Tras `202`: refresco inmediato y banner de parcialidad.

### 15.2. Parar

- Botón visible solo con estado `running` o `stopping`.
- Confirmación: «Se solicitará una parada ordenada. Los eventos ya confirmados se
  conservan».
- Tras la respuesta, refresco inmediato.
- Si no hay simulación activa, el backend devuelve `409` y se muestra el aviso.

### 15.3. Simulación activa

- Banner persistente: `SIM-X en curso · 640/1060 publicados`.
- El selector sigue libre para consultar otras simulaciones.
- Los contadores de la simulación activa se marcan como parciales.
- Al terminar, el banner desaparece y el estado pasa a `En directo`.

---

## 16. Polling y actualización

- Intervalo: **5 segundos**.
- Se pausa con `document.hidden` y se reanuda al volver a la pestaña.
- Se refresca inmediatamente después de:
  - crear una configuración;
  - arrancar;
  - parar;
  - cambiar de simulación;
  - cambiar de página o intervalo.
- Botón `Actualizar` para refresco manual.
- Un ciclo lanza en paralelo:
  - `GET /api/simulations`;
  - `GET /api/simulations/{sim}/summary`;
  - `GET /api/simulations/{sim}/flights?limit=20&offset=…`;
  - `GET /api/simulations/{sim}/timeline?interval=…`;
  - `GET /api/simulations/status`.
- Se usa `Promise.allSettled`; si falla un bloque, se conserva su último dato bueno y se
  marca obsoleto, sin tirar los demás.
- Si falla todo, el banner global pasa a `Sin conexión`.
- No se solapan ciclos: si el anterior no ha terminado, se omite el nuevo.
- `AbortController` con timeout de 10 s por petición.

---

## 17. Estados de la interfaz

### 17.1. Estado global

| Estado | Cuándo | Cabecera | Banner |
|---|---|---|---|
| Cargando | Primera carga | Pill gris «Cargando» | No |
| En directo | Último ciclo correcto y sin simulación activa | Verde «En directo» | No |
| Parcial | Simulación `running`/`stopping` | Ámbar «Parcial» | «Resultados parciales: N/M publicados» |
| Sin conexión | Al menos una llamada esencial falla | Rojo «Sin conexión» | Error con hora del fallo |
| Vacío | La simulación no tiene salidas | Verde/neutro | «Sin salidas almacenadas para esta simulación» |

### 17.2. Matriz por bloque

| Bloque | Cargando | Vacío | Parcial | Error | Obsoleto |
|---|---|---|---|---|---|
| Selector | Skeleton de una línea | «No hay configuraciones» | Sin cambio | Conserva opciones; marca fallo | Atenuado |
| Métricas | 4 skeletons | Cuatro tarjetas a 0, porcentaje `—` | Etiqueta «Parcial» en el bloque | Conserva últimas y atenúa | Hora de último éxito |
| Muelle | 5 skeletons | Cinco tarjetas con umbral/terminal y 0 | Etiqueta «Parcial» | Conserva últimas y atenúa | Borde gris |
| Evolución | Skeleton de gráfica | Ejes + «Sin salidas en este intervalo» | Etiqueta «Parcial» | Conserva última gráfica atenuada | Nota de obsoleto |
| Tabla | Skeleton de 5 filas | «Sin salidas almacenadas» | Etiqueta «Parcial» | Conserva página anterior atenuada | Nota de obsoleto |
| Config actual | Skeleton de secciones | No aplica: siempre hay configuración | Sin cambio | Error dentro del cajón | No aplica |
| Formulario | No aplica | No aplica | No aplica | Errores por campo | No aplica |

### 17.3. Frescura

- Cada bloque muestra su hora de último éxito en una línea secundaria.
- La cabecera muestra la hora global del último ciclo correcto.
- Si un bloque falla, su hora se conserva y se añade «sin actualizar desde …».
- Los datos obsoletos se atenúan con opacidad 0,65 y un borde discontinuo; nunca se
  borran.

### 17.4. Mensajes exactos

- Sin salidas: `Sin salidas almacenadas para esta simulación.`
- Parcial: `Resultados parciales: NiFi sigue insertando. Los contadores pueden crecer.`
- Error de API: `No se pudo actualizar. Último dato correcto: HH:MM:SS UTC.`
- Sin conexión: `Sin conexión con la API. Se muestran los últimos datos disponibles.`
- Conflicto al arrancar: `Ya hay una simulación en curso: SIM-…`.
- Configuración guardada: `Configuración SIM-… guardada.`

El microcopy puede ajustarse en implementación sin cambiar la arquitectura.

---

## 18. Contrato con la API

### 18.1. Endpoints usados

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/health` | Comprobación opcional de vida |
| `GET` | `/api/simulations?limit=100&offset=0` | Selector y metadatos |
| `GET` | `/api/configurations/{id}` | Pestaña de configuración actual |
| `POST` | `/api/configurations` | Alta de configuración |
| `GET` | `/api/simulations/{id}/summary` | Métricas globales y por puerta |
| `GET` | `/api/simulations/{id}/flights?limit=20&offset=0` | Tabla paginada |
| `GET` | `/api/simulations/{id}/timeline?interval=hour\|day` | Gráfica |
| `GET` | `/api/simulations/status` | Estado de la ejecución |
| `POST` | `/api/simulations/{id}/start` | Arrancar |
| `POST` | `/api/simulations/stop` | Parar |

No se usa `test-events` en la interfaz; queda para pruebas manuales.

### 18.2. Cambio 1: `summary.totals`

Se mantiene la forma actual y se añade un bloque `totals`:

```json
{
  "simulation_id": "SIM-01",
  "partial": false,
  "totals": {
    "valid_departures": 1007,
    "above_threshold": 374,
    "above_threshold_percentage": 37.14,
    "distinct_aircraft": 50
  },
  "gates": [
    {
      "gate_id": "G1",
      "name": "Puerta 1",
      "terminal_id": "T1",
      "delay_threshold_minutes": 15,
      "valid_departures": 257,
      "above_threshold": 87,
      "above_threshold_percentage": 33.85
    }
  ]
}
```

Reglas:

- `above_threshold` usa el mismo `>` estricto que Dremio.
- `valid_departures` cuenta solo `record_valid=true`.
- `distinct_aircraft` se calcula sobre el total de la simulación; no es la suma de las
  puertas.
- `above_threshold_percentage` se redondea a dos decimales en el backend; la web
  muestra uno.
- Si no hay salidas, `distinct_aircraft=0` y el porcentaje `0.0`; la web muestra `—`.

### 18.3. Cambio 2: `timeline.items[].above_threshold`

Cada item mantiene `departures` y añade `above_threshold`:

```json
{
  "simulation_id": "SIM-01",
  "basis": "actual_departure_at",
  "timezone": "UTC",
  "interval": "hour",
  "items": [
    {
      "timestamp": "2026-10-05T08:00:00Z",
      "departures": 24,
      "above_threshold": 9
    }
  ]
}
```

La agregación usa la misma regla de retraso y umbral. No se guardan cálculos en MongoDB.

### 18.4. Respuestas existentes relevantes

`GET /api/simulations`:

```json
{
  "items": [
    {
      "simulation_id": "SIM-01",
      "name": "Aeropuerto simulado Bahía de Cádiz",
      "last_emitted_at": "2026-10-11T21:59:00Z",
      "stored_departures": 1007,
      "partial": false
    }
  ],
  "total": 4,
  "limit": 100,
  "offset": 0
}
```

`GET /api/simulations/{id}/flights`:

```json
{
  "simulation_id": "SIM-01",
  "items": [
    {
      "event_id": "EV-SIM-01-000123",
      "flight_number": "A01143",
      "airline": "Aero01",
      "aircraft_model": "Modelo A",
      "destination_id": "DEST-03",
      "gate_id": "G1",
      "terminal_id": "T1",
      "scheduled_departure_at": "2026-10-11T13:56:00Z",
      "actual_departure_at": "2026-10-11T14:20:00Z",
      "emitted_at": "2026-11-02T18:45:15Z",
      "delay_minutes": 24.0,
      "delay_threshold_minutes": 15,
      "exceeds_threshold": true,
      "record_valid": true
    }
  ],
  "total": 1007,
  "limit": 20,
  "offset": 0
}
```

`GET /api/simulations/status`:

```json
{
  "state": "running",
  "simulation_id": "SIM-01",
  "published": 640,
  "total": 1060,
  "started_at": "2026-11-02T18:00:00+00:00",
  "finished_at": null,
  "last_error": null
}
```

### 18.5. Errores

| Código | Tratamiento |
|---|---|
| `404` | La simulación ya no existe: aviso y volver a la selección válida |
| `409` | Conflicto al arrancar o duplicado al crear: mensaje concreto |
| `422` | Errores por campo en el formulario |
| `503` | MongoDB no disponible: banner y reintento |
| Red/timeout | Bloque obsoleto; banner global si afecta a varias llamadas |

### 18.6. Límites

- Tabla: 20 filas por página; máximo de la API 200, pero la web no lo usa.
- Selector: 100 configuraciones; suficiente para el proyecto.
- Timeline: como máximo 31 días × 24 horas; se filtra por simulación.
- No se descarga la colección completa de `vuelos`.

---

## 19. Formato y unidades

- Fechas y horas: `YYYY-MM-DD HH:MM UTC` en tablas y tarjetas.
- En el JSON y en el detalle técnico: ISO 8601 completo.
- La zona horaria de la configuración sigue siendo `Europe/Madrid`, pero la interfaz
  muestra UTC por decisión de diseño.
- Retraso: minutos, con una decimal si no es entero.
- Umbral: minutos enteros.
- Porcentaje: un decimal, coma decimal española.
- Miles: punto español (`1.007`).
- `null` se muestra como `—`.
- Los valores negativos anómalos se marcan como error de dato, no se ocultan.

---

## 20. Accesibilidad

- Enlace `Saltar al contenido`.
- Todos los controles alcanzables con teclado.
- Foco visible con `outline` de 2 px y contraste.
- `aria-live="polite"` para estado, última actualización y toasts; `role="alert"` para
  errores críticos.
- Cajón y modales con foco atrapado y restauración al elemento de origen.
- Tabla con `caption`, `thead`, `th scope="col"` y filas legibles.
- El estado de superación no depende solo del color: incluye texto e icono.
- `prefers-reduced-motion` desactiva scroll suave y transiciones.
- Contraste mínimo AA en textos y controles.
- Objetivos táctiles de al menos 44 × 44 px en móvil.

---

## 21. Seguridad y despliegue

### 21.1. Servidor

- FastAPI sirve `web/` con `StaticFiles` en `/`.
- Los assets viven en `web/assets/`.
- La API sigue en `/api/*`.
- No hay CORS entre frontend y API: mismo origen.

### 21.2. systemd

Unidad `aeroflow-backend.service`:

```ini
[Unit]
Description=AeroFlow backend
After=network.target

[Service]
User=pablo
WorkingDirectory=/home/pablo/backend_aeroflow
EnvironmentFile=/home/pablo/backend_aeroflow/.env
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- Un solo worker: el estado de la simulación vive en memoria.
- El puerto 8000 se restringe en el firewall; solo Traefik debe alcanzarlo.
- El `.env` no se versiona.

### 21.3. Traefik

- Router `aeroflow` en `Host(aeroflow.monolith.dynamic-dns.net)`.
- Entrada `websecure`, TLS con `certResolver: myresolver`.
- Servicio a `http://172.18.0.1:8000` (gateway de Docker hacia la VM).
- Middleware `aeroflow-auth` con basic auth.
- El hash se guarda en `dynamic.yml`, como se acordó; la contraseña en claro no se
  escribe en el repositorio ni en la documentación.
- Si el hash se publica accidentalmente, se rota.

### 21.4. Cabeceras

FastAPI añade:

- `Content-Security-Policy`:
  `default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
- `X-Content-Type-Options: nosniff`.
- `Referrer-Policy: no-referrer`.
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`.

### 21.5. Escritura

- Basic auth protege el acceso.
- Las rutas de escritura (`POST /api/configurations`, `start`, `stop`) comprueban
  `Origin`/`Sec-Fetch-Site` para aceptar solo mismo origen.
- No se añade login propio ni tokens en el navegador.

---

## 22. Plan de implementación

### Fase 1 · Contrato backend

- Añadir `totals` a `summary`.
- Añadir `above_threshold` a cada bucket de `timeline`.
- Tests de agregación y del catálogo fijo.
- Verificar que `SIM-01` sigue dando 1.007 / 374 y 50 aviones.

### Fase 2 · Shell y estilos

- Crear `web/index.html`, `web/assets/styles.css`.
- Tokens, cabecera, rejilla, tarjetas y estados vacíos.
- Montar `StaticFiles` en FastAPI.

### Fase 3 · Cliente API, estado y polling

- `api.js`, `state.js`, `polling.js`, `format.js`.
- `Promise.allSettled`, timeout, pausa por visibilidad.
- Banner global y frescura por bloque.

### Fase 4 · Cabecera y controles

- Selector, pill de estado, última actualización.
- Refresco manual, configuración, arrancar/parar.
- Modales de confirmación y toasts.

### Fase 5 · Métricas y muelle

- Cuatro tarjetas globales.
- Cinco tarjetas de puerta con barras locales y clic para filtrar.
- Estado vacío completo.

### Fase 6 · Evolución

- SVG de barras apiladas.
- Selector hora/día.
- Leyenda, tooltips y estado sin datos.

### Fase 7 · Tabla

- Tabla paginada de 20 filas.
- Filtros de página y chip de puerta.
- Paginación reflejada en la URL.

### Fase 8 · Cajón y formulario

- Pestañas actual/nueva.
- Campos, terminales con intercambio, perfiles y JSON de solo lectura.
- Validación cliente + mapeo de 422.
- Guardar, duplicar, confirmación de cambios sin guardar.

### Fase 9 · Despliegue y pruebas

- `aeroflow-backend.service`.
- Router y basic auth de Traefik.
- Cabeceras CSP.
- Pruebas de humo, documentación y capturas para la memoria.

Cada fase termina con `pytest` en verde y una comprobación manual de la anterior.

---

## 23. Plan de pruebas

### 23.1. Backend

- `summary.totals` coincide con Dremio para `SIM-01`: 1.007, 374, 37,14 %, 50 aviones.
- `timeline` suma las mismas salidas y superaciones por bucket.
- El catálogo fijo sigue rechazando `DEST-05`.
- `SIM-POSTEND` sigue devolviendo 101 salidas y 101 superaciones.
- `SIM-VALID-API` y `SIM-FINAL` devuelven totales a cero sin error.

### 23.2. Humo manual

1. Cargar `/` y comprobar esqueleto, luego datos.
2. Cambiar de simulación y verificar URL y página 1.
3. Ver `SIM-VALID-API` o `SIM-FINAL`: panel completo a cero, puertas visibles.
4. Ver `SIM-POSTEND`: 101 salidas, 101 superaciones y avisos.
5. Cambiar hora/día en la gráfica.
6. Paginar y comprobar `?page=`.
7. Filtrar por puerta desde el muelle y limpiar.
8. Abrir configuración actual y el JSON plegable.
9. Duplicar, cambiar umbral/terminal, guardar y comprobar nueva simulación.
10. Intentar guardar con un terminal duplicado: debe impedirse.
11. Arrancar con confirmación y ver banner parcial/progreso.
12. Parar con confirmación.
13. Detener el backend y comprobar banner, atenuación y recuperación.
14. Probar 390 px, 768 px y 1440 px.
15. Recorrer con teclado y comprobar foco y `aria-live`.

### 23.3. Pruebas funcionales del enunciado

- **5. Configuración desde la web:** crear una configuración, verla en `operativos`,
  arrancarla y comprobar que se usa; la anterior se conserva.
- **6. Nuevas salidas:** arrancar, ver crecer contadores, refrescar y comprobar la tabla
  y la gráfica.

Las pruebas 1–4 se documentan con NiFi/Mongo/Dremio y no dependen de esta web.

---

## 24. Riesgos y límites conocidos

- **`summary` sin totales:** hasta la fase 1, el frontend no puede mostrar aviones
  distintos globales sin una consulta extra. El diseño asume el cambio.
- **`timeline` sin superaciones:** hasta la fase 1, la gráfica solo podría apilar una
  serie. El diseño asume el cambio.
- **`SIM-NIFI-TEST` no aparece:** no tiene configuración en `operativos`. Es una
  decisión consciente; se documenta en la guía.
- **`SIM-POSTEND` no es analítica:** tiene 101 salidas y todas superan el umbral; sirve
  para demostrar avisos y resultados parciales.
- **Filtros de página:** no buscan en todo el histórico; para eso está Power BI.
- **Basic auth única:** no hay roles; cualquier usuario puede escribir. Es suficiente
  para la entrega, pero no para producción real.
- **Sin WebSocket:** el crecimiento se ve por polling de 5 s; el enunciado lo permite.
- **Sin tests de navegador:** se compensa con humo manual documentado y tests de
  backend.

---

## 25. Criterio de aceptación del diseño

El diseño se considera cerrado cuando:

- la estructura de pantalla y el orden de bloques están aprobados;
- el cajón y sus dos pestañas están definidos;
- los campos editables y de solo lectura están delimitados;
- los estados de carga, vacío, parcial, error y obsoleto tienen comportamiento;
- el contrato de `summary` y `timeline` está acordado;
- el despliegue con systemd, Traefik y basic auth está decidido;
- el plan de fases y las pruebas están aceptados.

Con esto, la implementación puede empezar por la fase 1 sin volver a decidir
arquitectura.
