# Informe Power BI de AeroFlow

Tres páginas sobre las vistas de Dremio, en **DirectQuery**, filtradas a `SIM-01`.

## Qué hay aquí

```
AeroFlow.pbip                      ← abre este fichero
AeroFlow.Report/                   ← definición del informe (formato PBIR)
AeroFlow.SemanticModel/            ← modelo semántico (TMDL) con la conexión a Dremio
herramientas/generar-informe.py    ← genera las 3 páginas y el modelo
herramientas/generar-prueba-d9.py  ← genera la prueba mínima de D9
```

El formato PBIP es texto plano: modelo en TMDL, páginas y visuales en JSON.
Se puede versionar en Git y revisar; un `.pbix` no.

## Cómo abrirlo

Doble clic en `AeroFlow.pbip`. Si Windows no asocia la extensión, abre Power BI
Desktop y usa **Archivo → Abrir**.

Con el informe abierto, guárdalo como `.pbix` (**Archivo → Guardar como**) para
tener el fichero de entrega.

> Requiere Power BI Desktop 2.159 o superior (versión de Microsoft Store), que
> incluye el conector `Dremio.pqx` y el driver ADBC. **No** hace falta el driver
> ODBC de Dremio.

## Páginas

### 1. Estado general
Cinco tarjetas (salidas válidas, aviones distintos, superaciones, aviones con
exceso) y dos gráficos de barras por puerta (superaciones y salidas).

Fuentes: `D9_aviones_con_superacion`, `D2_pct_sobre_umbral_puerta`.

### 2. Patrones temporales
Evolución diaria de salidas (líneas), superaciones por franja horaria y salidas
por tipo de día.

Fuentes: `D4b_evolucion_diaria`, `D3_horas_franjas`, `D4_laborables_fin_semana`.

### 3. Compañías y aviones
Cuatro tarjetas, superaciones por compañía, salidas por modelo, superaciones por
puerta y compañía (con serie), y una tabla de puerta/destino con muestra y exceso.

Fuentes: `D5_companias`, `D5b_companias_por_puerta`, `D6_retraso_medio_magnitud`,
`D7_aviones_repetidos_dia`, `D8_compania_modelo`.

## Decisiones de diseño

**Sin DAX.** El informe no declara ni una medida. Todos los valores son
agregaciones implícitas del motor (`Sum`). El filtro de simulación es un filtro
de página categórico, no una medida calculada.

Consecuencia a tener en cuenta: sin DAX no hay `DISTINCT COUNT`. Por eso las
tarjetas usan sumas, que sí son aditivas y correctas, y **no** se usan recuentos
de columnas de texto ni de fechas. Los totales de aviones distintos y de
compañías salen de las vistas D9 y D5, que ya vienen preagregadas por Dremio.

**Sin KPI.** Los indicadores son visuales `card`, como se pidió.

**Sin visuales de Python.** No es una decisión estética: los visuales de
Python y R **no admiten DirectQuery**, porque necesitan el conjunto de datos
materializado en local. Además Microsoft retira R y Python visuals en mayo de
2027. Las gráficas son visuales nativos (`clusteredBarChart`,
`clusteredColumnChart`, `lineChart`, `tableEx`).

**Filtro único por página.** Cada página filtra `simulation_id = 'SIM-01'`, así
ningún visual necesita filtros propios y se evidencia la coherencia con las
cifras de referencia.

### Trampa de los literales en los filtros

Los valores de texto de un filtro van entre **comillas simples dentro** del
literal, y esto no es cosmético:

```json
"Values": [[{"Literal": {"Value": "'SIM-01'"}}]]   // correcto
"Values": [[{"Literal": {"Value": "SIM-01"}}]]     // falla
```

Sin las comillas, Power BI intenta interpretar el valor como identificador y la
representación del informe aborta con un `TypeError` en
`SQExprValidationVisitor.visitIn`. El síntoma es un error de JavaScript al
pintar, no un mensaje de validación, así que el validador de esquemas **no lo
detecta**: el JSON es válido, la expresión no.

La forma correcta se puede comprobar con el codificador oficial:

```bash
npx powerbi-report-author expr encode "SIM-01" --kind string
# -> {"Literal": {"Value": "'SIM-01'"}}
```

Regla práctica: enteros con sufijo `L` (`"2022L"`), texto con comillas simples
(`"'SIM-01'"`), comillas simples internas duplicadas (`"'O''Brien'"`).

## Conexión

La consulta M de cada tabla sigue este patrón:

```m
let
    Origen = Dremio.DatabasesV370("adbc://192.168.0.26:32010", "Disabled"),
    Aeroflow = Origen{[Name="Aeroflow",Kind="Schema"]}[Data],
    Vista = Aeroflow{[Name="D2_pct_sobre_umbral_puerta",Kind="Table"]}[Data]
in
    Vista
```

- El prefijo **`adbc://`** es obligatorio: sin él el conector usa ODBC.
- Dremio separa los dos protocolos en puertos distintos, y confundirlos es el
  error más fácil de cometer:

  | Puerto | Protocolo | Driver |
  |---|---|---|
  | `31010` | ODBC / JDBC (con TLS) | externo, **no** instalado |
  | `32010` | Arrow Flight (sin TLS) | ADBC, **incluido** en Power BI |

  El error `[Microsoft][Drill] ... No handshake` aparece cuando el conector va
  por ODBC contra el puerto de Flight.
- Credenciales: usuario `pablo`.

## Validación

```bash
npm install @microsoft/powerbi-report-authoring-cli
npx powerbi-report-author validate powerbi
```

Resultado: **0 errores, 0 avisos** (18 visuales).

Esa herramienta valida la definición del informe contra los esquemas de
Microsoft. El TMDL no lo valida: lo valida Power BI al abrir.

## Comprobaciones hechas antes de entregar

| Comprobación | Resultado |
|---|---|
| Esquemas PBIR (Microsoft) | 0 errores, 0 avisos |
| Todos los campos de los visuales existen en el modelo | 18/18 |
| Solapes y desbordes de página | ninguno (1280×720) |
| Cifras contra Dremio (SIM-01) | 1.007 salidas, 374 superaciones, 50 aviones |

## Cifras de referencia (SIM-01)

| Métrica | Valor |
|---|---|
| Salidas válidas | 1.007 |
| Aviones distintos | 50 |
| Superaciones | 374 (37,14 %) |
| Aviones con exceso | 50 (100 %) |
| Por puerta (superan/salidas) | G1 93/257 · G2 50/183 · G3 68/224 · G4 128/206 · G5 35/137 |

## Regenerar

```bash
python3 herramientas/generar-informe.py
npx powerbi-report-author validate powerbi
```

El generador reescribe `definition/pages/` y las tablas del modelo. Si añades
algún visual, hazlo en el script y vuelve a ejecutarlo, no a mano.

## Formato del modelo semántico

El modelo usa **TMDL** (carpeta `definition/` con ficheros `.tmdl`), no TMSL, y
por eso `definition.pbism` declara `"version": "4.2"`.

Si `definition.pbism` lleva `"version": "1.0"`, Power BI interpreta que el modelo
es TMSL y busca un `model.bim` inexistente, fallando con
`Missing required artifact 'model.bim'`. La versión del fichero y el formato de
la carpeta tienen que coincidir.
