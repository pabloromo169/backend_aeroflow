# Guía: centro de control web de AeroFlow

El centro de control es la aplicación web del proyecto: consulta MongoDB a través
de la API FastAPI, muestra la simulación en curso y permite preparar la
configuración de la siguiente. Esta guía recoge **dónde está desplegada**, **cómo
se compone**, **cómo se verificó** y **la evidencia de las pruebas funcionales 5 y
6** que pide el enunciado.

- Repositorio: `backend_aeroflow`
- Código de la interfaz: `web/`
- Diseño y decisiones de interfaz: `web/DESIGN.md`
- Capturas: `docs/capturas-web/`

---

## 1. URL desplegada

| Elemento | Valor |
|---|---|
| URL pública | `https://aeroflow.monolith.dynamic-dns.net/` |
| Autenticación | basic auth en Traefik (usuario `aeroflow`) |
| Acceso interno | `http://127.0.0.1:8000/` y `http://192.168.0.26:8000/` |
| Servicio | `aeroflow-backend.service` (systemd, uvicorn en `0.0.0.0:8000`) |
| Certificado | Let's Encrypt, gestionado por Traefik |
| Ruta del cajón | `https://aeroflow.monolith.dynamic-dns.net/?panel=config&sim=SIM-01` |

El puerto `8000` está cerrado desde la LAN: solo Traefik, que corre en el host y
llega por el puente de Docker (`172.18.0.1`), alcanza el backend. Sin credenciales,
la URL pública devuelve `401`.

La contraseña no se documenta aquí ni se versiona: el hash bcrypt vive en
`traefik-docker/dynamic/aeroflow.yml`, fuera del repositorio, y se regenera con
`htpasswd -nbB aeroflow 'CONTRASEÑA'`.

---

## 2. Composición

La interfaz es HTML, CSS y módulos ES nativos. **No hay npm, bundler ni paso de
compilación**: FastAPI sirve los archivos tal cual.

```
web/
├── index.html              estructura de la página, cajón y diálogos
├── DESIGN.md               paleta, tipografía y decisiones de diseño
└── assets/
    ├── tokens.css          variables de color, espaciado, tipografía y sombras
    ├── base.css            reinicio, tipografía base y contenedor
    ├── styles.css          componentes (cabecera, métricas, puertas, gráfica, tabla, cajón)
    └── js/
        ├── main.js         arranque, estado y sondeo cada 5 s
        ├── api.js          cliente de la API
        ├── state.js        estado y URL (?sim, ?page, ?interval, ?panel)
        ├── metrics.js      tarjetas de totales y puertas
        ├── charts.js       gráfica de evolución en SVG
        ├── table.js        panel de últimas salidas
        ├── render.js       avisos de estado y resultados parciales
        ├── config-panel.js pestaña «Configuración actual»
        ├── config-form.js  pestaña «Nueva simulación»
        └── dialogs.js      cajón, diálogo de confirmación y avisos
```

### Estados de la interfaz

| Estado | Cómo se llega | Qué se ve |
|---|---|---|
| Normal | `/?sim=SIM-01` | Totales, cinco puertas, gráfica y tabla |
| Sin datos | `/?sim=SIM-FINAL` | Estado vacío con explicación, sin gráfica |
| Parcial | Simulación en curso | Franja «Resultados parciales: NiFi sigue insertando» |
| Cajón | `/?panel=config&sim=…` | Configuración actual y formulario de alta |
| Error de API | API caída | Mensaje de error, conserva los últimos datos |

El estado vive en la URL, así que cualquier vista concreta se puede enlazar o
recargar sin perderla: `?sim=`, `?page=`, `?interval=hour|day`, `?panel=monitor|config`.

### Comportamiento

- Sondeo cada 5 s; se pausa con `document.hidden` y refresca de inmediato tras
  iniciar o detener una simulación.
- `Promise.allSettled`: si falla el resumen pero responde la tabla, la vista no se
  rompe entera.
- Las horas se muestran siempre en UTC con el formato `YYYY-MM-DD HH:MM UTC`.
- Los contadores y las superaciones los calcula el backend a partir de las fechas
  y del umbral de cada registro; MongoDB no guarda esos cálculos.
- El selector solo lista configuraciones guardadas en `operativos`.
- El alta parte de la configuración seleccionada, se puede editar y **no arranca**
  la simulación: solo la guarda para la siguiente ejecución.

---

## 3. Despliegue

```bash
sudo cp deploy/aeroflow-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aeroflow-backend
systemctl status aeroflow-backend
```

El router de Traefik está en `deploy/traefik-aeroflow.yml`: `Host` del dominio,
servicio hacia `http://172.18.0.1:8000` y middleware de basic auth.

### Arranque degradado

Si MongoDB no responde al arrancar, la API **no aborta**: queda escuchando,
devuelve `503` en `/health` y reintenta los índices y la configuración semilla cada
15 s en segundo plano. Antes esto provocaba un bucle de reinicios de systemd
(2.780 reinicios acumulados, unos 295 por hora). La unidad además limita el bucle:

| Directiva | Valor |
|---|---|
| `Restart` | `always` |
| `RestartSec` | `10` |
| `StartLimitIntervalSec` | `300` |
| `StartLimitBurst` | `5` |

Comprobación rápida del servicio:

```bash
systemctl show aeroflow-backend -p ActiveState -p NRestarts
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/health
```

---

## 4. Verificación realizada

Comprobaciones sobre la URL pública, con Chromium headless real (Playwright),
sesión autenticada y zona horaria UTC.

| Comprobación | Resultado |
|---|---|
| Totales de `SIM-01` | 1.007 salidas, 374 superaciones (37,14 %), 50 aviones |
| Puertas | G1 257/93, G2 183/50, G3 224/68, G4 206/128, G5 137/35 |
| Barras de la gráfica | 167 (intervalo por hora) |
| Filas de la tabla | 20 por página, 51 páginas |
| Ancho 390 px | Sin scroll horizontal, puertas y métricas a 1 columna |
| Ancho 768 px | Sin scroll horizontal, 2 columnas |
| Ancho 1024 px | Sin scroll horizontal, 3 columnas de puertas y 4 métricas |
| Ancho 1440 px | Sin scroll horizontal, 5 puertas en una fila |
| Cajón | Abre con foco dentro, `Escape` lo cierra y devuelve el foco |
| Consola del navegador | Sin errores en ninguno de los cuatro anchos |
| `/health` | `200` en local y `200` a través de Traefik |
| URL sin credenciales | `401` |
| Reinicios del servicio | `0` desde la instalación de la unidad corregida |

Pruebas automáticas del backend:

```bash
.venv/bin/python -m pytest -q
# 41 passed
```

Incluyen dos pruebas nuevas del arranque degradado: el API sobrevive a MongoDB
inalcanzable y sirve `503`, y se recupera cuando MongoDB vuelve.

---

## 5. Prueba funcional 5: configuración desde la web

Objetivo del enunciado: guardar una configuración nueva en `operativos`, que el
simulador la use en la siguiente ejecución y que la anterior se conserve.

Se creó desde la web una configuración llamada **`PRUEBA_01`**, con
`simulation_id` **`SIM-E376B9557D94`**, partiendo de `SIM-01` y modificando dos
cosas:

| Parámetro | `SIM-01` (original) | `PRUEBA_01` (nueva) |
|---|---|---|
| Umbral `G1` | 15 min | **20 min** |
| Terminal de `G4` | T4 | **T5** |
| Terminal de `G5` | T5 | **T4** |
| Semilla | 42 | 42 |
| Salidas / superaciones | 1.007 / 374 | 1.007 / **393** |
| Porcentaje | 37,14 % | **39,03 %** |

Resultado:

- La configuración quedó guardada en `operativos` con un `simulation_id` distinto
  generado por el backend, y aparece en el selector de la web.
- `SIM-01` **sigue intacta** con sus 1.007 vuelos y 374 superaciones: las
  configuraciones anteriores se conservan.
- El intercambio de terminales se refleja en la vista: `G4` figura en `T5` y `G5`
  en `T4`.
- El cambio de umbral se refleja en los contadores por puerta:

| Puerta | `SIM-01` válidas/superan | `PRUEBA_01` válidas/superan |
|---|---|---|
| G1 (umbral 15 → 20) | 257 / 93 | 233 / 87 |
| G2 | 183 / 50 | 184 / 66 |
| G3 | 224 / 68 | 236 / 74 |
| G4 | 206 / 128 | 205 / 120 |
| G5 | 137 / 35 | 149 / 46 |

`G1` baja de 93 a 87 superaciones al subir el umbral, mientras las puertas con el
mismo umbral mantienen su comportamiento. El total de válidas no cambia (1.007)
porque el reparto de puertas no altera el conjunto de vuelos, solo su etiqueta.

- La simulación nueva no se arranca automáticamente al guardar: el formulario solo
  prepara la siguiente ejecución, como pide el enunciado.

Evidencia visual: `docs/capturas-web/prueba-funcional-5.png`.

### Nota sobre reenvíos

Repetir una simulación ya cargada no crea filas nuevas: `event_id` es determinista
y `vuelos` tiene un índice único sobre ese campo, así que el reenvío se resuelve
como conflicto de unicidad y se descarta. Es el mismo comportamiento que demuestra
la prueba funcional 2.

---

## 6. Prueba funcional 6: nuevas salidas visibles

Objetivo del enunciado: comprobar que las salidas nuevas aparecen al actualizar la
web y refrescar las visualizaciones, identificando los resultados como parciales
mientras dura la ingesta.

Comportamiento comprobado:

1. Una simulación en marcha devuelve `partial: true` en el resumen y la interfaz
   muestra la franja **«Resultados parciales: NiFi sigue insertando. Los contadores
   pueden crecer.»**
2. La vista se refresca sola cada 5 s, sin recargar la página, y los contadores de
   salidas válidas, superaciones y aviones distintos crecen con cada ingesta.
3. La tabla se reordena por `emitted_at` descendente: las salidas nuevas aparecen
   arriba.
4. La gráfica se recalcula con el nuevo intervalo, agrupando por hora efectiva de
   salida en UTC.
5. Al terminar la ingesta, `partial` pasa a `false` y la franja desaparece: los
   contadores dejan de moverse.
6. Si se está mirando una simulación distinta de la que se está ejecutando, la
   franja lo dice explícitamente: *«… en curso. Estás viendo …; sus datos no son
   parciales.»*

Los contadores por puerta y los totales coinciden con lo almacenado en MongoDB,
porque el backend los calcula en cada consulta a partir de las fechas y del umbral.

---

## 7. Capturas

Todas están en `docs/capturas-web/`, tomadas contra la URL pública con datos reales.

| Archivo | Contenido |
|---|---|
| `escritorio-1440.png` | Página completa en escritorio |
| `escritorio-1440-sin-scroll.png` | Primera pantalla: cabecera, totales y puertas |
| `tablet-768.png` | Rejilla a dos columnas |
| `movil-390.png` | Vista móvil a una columna |
| `cajon-configuracion.png` | Cajón, pestaña «Configuración actual» |
| `formulario-nueva.png` | Cajón, pestaña «Nueva simulación» |
| `estado-vacio.png` | Simulación sin salidas (`SIM-FINAL`) |
| `filtro-puerta-g1.png` | Tabla filtrada por la puerta G1 |
| `prueba-funcional-5.png` | `PRUEBA_01`, evidencia de la prueba 5 |

---

## 8. Estado actual de la base

| Colección | Documentos |
|---|---:|
| `operativos` | 5 (`SIM-01`, `SIM-E376B9557D94`, `SIM-FINAL`, `SIM-POSTEND`, `SIM-VALID-API`) |
| `vuelos` de `SIM-01` | 1.007 |
| `vuelos` de `SIM-E376B9557D94` (`PRUEBA_01`) | 1.007 |
| `vuelos` de `SIM-POSTEND` | 101 |
| `vuelos` de `SIM-NIFI-TEST` | 1 |
| **Total `vuelos`** | **2.116** |

`SIM-NIFI-TEST` no tiene configuración en `operativos` y por eso no aparece en el
selector: es el documento de prueba del flujo de NiFi y se conserva a propósito.
`SIM-VALID-API` y `SIM-FINAL` están vacías de forma deliberada y sirven para
comprobar los estados sin datos y las puertas con cero salidas.

`SIM-E376B9557D94` se conserva como evidencia de la prueba funcional 5. Si en algún
momento se quisiera retirar, basta con borrar su configuración y sus vuelos por
`simulation_id`, sin afectar a `SIM-01`.

---

## 9. Problemas conocidos

- **Caché del navegador:** tras cambiar el CSS, la primera carga puede mostrar el
  aspecto anterior. Se resuelve con recarga forzada (`Ctrl+Shift+R`).
- **Sondeos ajenos en el journal:** aparecen `404` periódicos de `/v1/models` desde
  `127.0.0.1`. No vienen de la aplicación.
- **Un solo worker:** uvicorn se ejecuta con `--workers 1` porque el estado y la
  coordinación de la ejecución viven en memoria.
