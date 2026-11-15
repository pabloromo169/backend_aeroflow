# Informe Power BI de AeroFlow

Prueba mínima: **una página con una tarjeta** que muestra `D9` (`valid_departures`)
de la simulación `SIM-01`, leída **en DirectQuery** desde las vistas de Dremio.

Valor esperado: **1007**.

## Qué hay aquí

```
AeroFlow.pbip                      ← abre este fichero
AeroFlow.Report/                   ← definición del informe (formato PBIR)
AeroFlow.SemanticModel/            ← modelo semántico (TMDL) con la conexión a Dremio
```

El formato PBIP es texto plano: modelo semántico en TMDL y páginas/visuales en JSON.
Permite versionarlo en Git y revisarlo, cosa que un `.pbix` no permite.

## Cómo abrirlo

Doble clic en `AeroFlow.pbip`.

Si Windows no asocia la extensión, abre Power BI Desktop primero y usa
**Archivo → Abrir** sobre `AeroFlow.pbip`. Con el informe ya abierto, guárdalo
como `.pbix` (**Archivo → Guardar como**) para tener el fichero de entrega.

> Requiere una versión de Power BI Desktop que soporte PBIP y el conector
> `Dremio.pqx`, que viene incluido en la versión de Microsoft Store (2.159 o
> superior). No hace falta instalar el driver ODBC: el conector usa ADBC.

## Conexión

La consulta M está en `AeroFlow.SemanticModel/definition/tables/D9_aviones_con_superacion.tmdl`:

```m
let
    Origen = Dremio.DatabasesV370("adbc://192.168.0.26:32010", "Disabled"),
    Aeroflow = Origen{[Name="Aeroflow",Kind="Schema"]}[Data],
    Vista = Aeroflow{[Name="D9_aviones_con_superacion",Kind="Table"]}[Data]
in
    Vista
```

- El prefijo **`adbc://`** es obligatorio: sin él el conector usa ODBC.
- Dremio tiene **dos puertos distintos**, y confundirlos es el error más fácil de cometer:

  | Puerto | Protocolo | Uso |
  |---|---|---|
  | `31010` | ODBC / JDBC (TLS) | necesita el driver ODBC de Dremio instalado |
  | `32010` | Arrow Flight (sin TLS) | ADBC, driver incluido en Power BI |

  El conector ADBC usa `libadbc_driver_flightsql.dll`, que Power BI ya trae en
  `bin\ADBC Drivers\FlightSQL\`. No hay que instalar nada.

- Al abrir por primera vez pedirá credenciales de Dremio: usuario `pablo`.

## La medida

La tarjeta no usa la columna directamente, sino una medida que fija la simulación,
para que el valor sea único y no dependa de filtros:

```dax
CALCULATE(
    SUM(D9_aviones_con_superacion[valid_departures]),
    D9_aviones_con_superacion[simulation_id] = "SIM-01"
)
```

Esto es necesario porque el rol `Values` del visual `card` solo admite medidas.
El validador de PBIR rechaza una columna suelta ahí.

## Validación

El proyecto está validado con la herramienta oficial de Microsoft:

```bash
npm install @microsoft/powerbi-report-authoring-cli
npx powerbi-report-author validate powerbi
```

Resultado: **0 errores, 0 avisos**.

Esto cubre la definición del informe (`AeroFlow.Report`). El modelo semántico en
TMDL no lo valida esa herramienta: lo valida Power BI al abrirlo.

## Formato del modelo semántico

El modelo usa **TMDL** (carpeta `definition/` con ficheros `.tmdl`), no TMSL.
Por eso `definition.pbism` declara `"version": "4.2"`.

Detalle importante: si `definition.pbism` lleva `"version": "1.0"`, Power BI
interpreta que el modelo es TMSL y busca un `model.bim` que no existe, fallando
con `Missing required artifact 'model.bim'`. La versión del fichero y el formato
de la carpeta tienen que coincidir.


## Datos de referencia de D9

| simulation_id | valid_departures |
|---|---|
| SIM-01 | 1007 |
| SIM-E376B9557D94 | 1007 |
| SIM-POSTEND | 101 |
| SIM-NIFI-TEST | 1 |

## Siguiente paso

Cuando esta tarjeta se vea con 1007, se construyen las 3 páginas definitivas:
Estado general, Patrones temporales y Compañías y aviones. El mapeo de cada
visual a su vista de Dremio está en
`../GUIDE-dremio-fuente-mongodb-vistas.md` (§11.3).
