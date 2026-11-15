# Informe Power BI de AeroFlow

Tres páginas sobre las vistas de Dremio, en **DirectQuery**, filtradas a `SIM-01`.

## Qué hay aquí

```
AeroFlow.pbip                      ← abre este fichero
AeroFlow.Report/                   ← definición del informe (formato PBIR)
AeroFlow.SemanticModel/            ← modelo semántico (TMDL) con la conexión a Dremio
herramientas/generar-informe.py    ← genera las 3 páginas y el modelo
herramientas/generar-prueba-d9.py  ← genera la prueba mínima de D9
num3.png                           ← captura del estado anterior (referencia)
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
Cuatro tarjetas (salidas válidas, superaciones, aviones distintos, aviones con
exceso) y dos gráficos de barras por puerta, ordenados de mayor a menor, con
segmentación por puerta.

Fuentes: `D9_aviones_con_superacion`, `D2_pct_sobre_umbral_puerta`.

### 2. Patrones temporales
Evolución diaria de salidas (líneas), superaciones por franja horaria (con
segmentación) y salidas por tipo de día.

Fuentes: `D4b_evolucion_diaria`, `D3_horas_franjas`, `D4_laborables_fin_semana`.

### 3. Compañías y aviones
Cuatro tarjetas, superaciones por compañía (con segmentación), salidas por
modelo, superaciones por puerta y una tabla de puerta/destino.

Fuentes: `D5_companias`, `D5b_companias_por_puerta`, `D6_retraso_medio_magnitud`,
`D7_aviones_repetidos_dia`, `D8_compania_modelo`.

## Por qué cada visual lleva su propio filtro

Este es el punto clave del diseño y merece explicación, porque es contraintuitivo.

**El filtro de página no basta.** Las once tablas del modelo son vistas
preagregadas de Dremio y **no tienen relaciones entre sí**: no hay una tabla de
dimensiones común, cada una es independiente. En Power BI, un filtro de página
solo alcanza a la tabla por la que filtra. Si la página filtra por
`D9.simulation_id`, los visuales que usan `D5` o `D6` **no** quedan filtrados.

Ese fue el error de la primera versión y explica exactamente las cifras que se
veían mal:

| Métrica | Se mostraba | Correcto | Qué era en realidad |
|---|---|---|---|
| Salidas válidas (tabla) | 2.115 | **1.007** | suma de las 4 simulaciones |
| Superaciones (tabla) | 868 | **374** | suma de las 4 simulaciones |
| Excesos aviones (KPI) | 529 | **230** | suma de las 4 simulaciones |

Las tarjetas daban 1.007 porque usan `D9`, la misma tabla que el filtro de
página. Los demás visuales, al usar otras tablas, se mostraban sin filtrar.

**Solución:** cada visual declara un filtro categórico sobre
`simulation_id = 'SIM-01'` **de su propia tabla**. Son 20 filtros, uno por
visual, generados automáticamente por el script. Así los totales cuadran con
independencia de la tabla que use cada gráfico.

**Consecuencia para los segmentadores:** un slicer tampoco puede filtrar visuales
de otra tabla. Por eso los segmentadores están colocados junto a los visuales de
su misma tabla y solo afectan a esos. No es una limitación del diseño, es
consecuencia de que no haya relaciones. Si en el futuro se quisiera un filtro
global de verdad, habría que añadir una tabla de dimensiones y relaciones en el
modelo, y eso exige construirla en Dremio o con DAX.

## Otros errores corregidos

**Agregación de máximos.** El indicador «Exceso máximo» mostraba `40,43 mil`
porque se agregaba con `SUM` sobre una columna que ya es un máximo por grupo:
sumaba los máximos y daba 4.043. Lo correcto es `MAX`, que da **60**.
Regla aplicada en todo el modelo: `pct_*`, `avg_*` y `max_*` nunca se suman.

**Filas sin información.** La tabla de puerta/destino mostraba filas sin
superaciones (solo ruido de lectura). Se añadió un segundo filtro sobre
`note = 'Con superaciones'`.

**Leyenda ilegible.** El gráfico «Superaciones por puerta y compañía» tenía 50
series (5 puertas × 10 compañías) en un solo gráfico, con barras solapadas e
ilegibles. Se sustituyó por dos barras horizontales independientes y ordenadas:
una por puerta y otra por compañía. Se pierde el cruce puerta–compañía, pero el
cruce era ilegible y ese detalle ya lo aporta la tabla.

## Decisiones de diseño

**Sin DAX.** El informe no declara ni una medida. Todos los valores son
agregaciones implícitas del motor (`Sum`, `Avg`, `Max`).

Consecuencia a tener en cuenta: sin DAX no hay `DISTINCT COUNT` calculado. Por
eso las tarjetas usan las columnas ya agregadas de las vistas (`distinct_aircraft`,
`aircraft_with_exceedance`) en lugar de contar identificadores, que daría filas y
no valores distintos.

**Sin KPI.** Los indicadores son visuales `card`.

**Sin visuales de Python.** No es una decisión estética: los visuales de Python y
R **no admiten DirectQuery**, porque necesitan el conjunto de datos materializado
en local. Además Microsoft los retira en mayo de 2027. Las gráficas son visuales
nativos.

**Orden explícito.** Los gráficos de barras llevan `sortDefinition` descendente
por su medida, para que la lectura sea «de mayor a menor» y no alfabética.

**Etiqueta de agregación oculta en las tarjetas.** Power BI añade por defecto una
etiqueta con el nombre del campo agregado (`Suma de valid_departures`,
`Máximo de max_minutes_over`). Con nombres de campo largos se sale del cuadro y
queda cortada. Se oculta con `categoryLabels.show = false` y el valor se muestra
en su lugar a 32 pt y en negrita. El título de la tarjeta ya dice qué se mide,
así que la etiqueta era redundante además de ilegible.

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

## Trampa de los literales en los filtros

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

Regla práctica: enteros con sufijo `L` (`"2022L"`), texto con comillas simples
(`"'SIM-01'"`), comillas simples internas duplicadas (`"'O''Brien'"`).

## Validación

```bash
npm install @microsoft/powerbi-report-authoring-cli
npx powerbi-report-author validate powerbi
```

Resultado: **0 errores, 0 avisos** (20 visuales).

Esa herramienta valida la definición del informe contra los esquemas de
Microsoft. El TMDL no lo valida: lo valida Power BI al abrir.

## Comprobaciones hechas antes de entregar

| Comprobación | Resultado |
|---|---|
| Esquemas PBIR (Microsoft) | 0 errores, 0 avisos |
| Todos los campos de los visuales existen en el modelo | 20/20 |
| Todos los visuales filtran su propia tabla | 20/20 |
| Solapes y desbordes de página | ninguno (1280×720) |
| Cifras contra Dremio (SIM-01) | 1.007 y 374 en las tres páginas |
| Exceso máximo | 60 min (antes 40.430) |

## Cifras de referencia (SIM-01)

| Métrica | Valor |
|---|---|
| Salidas válidas | 1.007 |
| Aviones distintos | 50 |
| Superaciones | 374 (37,14 %) |
| Aviones con exceso | 50 (100 %) |
| Por puerta (superan/salidas) | G1 93/257 · G2 50/183 · G3 68/224 · G4 128/206 · G5 35/137 |

Ojo con las simulaciones: la base tiene datos de **cuatro** simulaciones
(`SIM-01`, `SIM-E376B9557D94`, `SIM-NIFI-TEST`, `SIM-POSTEND`), con 2.115 salidas
en total. Cualquier visual sin filtrar suma las cuatro. Los totales de todas
juntas (2.115 / 868) son correctos como tales, pero no son el análisis de
`SIM-01`, que es lo que pide el informe.

## Regenerar

```bash
python3 herramientas/generar-informe.py
npx powerbi-report-author validate powerbi
```

El generador reescribe `definition/pages/` y las tablas del modelo. Si añades
algún visual, hazlo en el script y vuelve a ejecutarlo, no a mano: el filtro por
tabla es fácil de olvidar, y olvidarlo vuelve a descuadrar las cifras.

## Formato del modelo semántico

El modelo usa **TMDL** (carpeta `definition/` con ficheros `.tmdl`), no TMSL, y
por eso `definition.pbism` declara `"version": "4.2"`.

Si `definition.pbism` lleva `"version": "1.0"`, Power BI interpreta que el modelo
es TMSL y busca un `model.bim` inexistente, fallando con
`Missing required artifact 'model.bim'`. La versión del fichero y el formato de
la carpeta tienen que coincidir.
