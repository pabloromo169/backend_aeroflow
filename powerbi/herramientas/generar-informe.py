#!/usr/bin/env python3
"""Genera las 3 paginas del informe AeroFlow en formato PBIR.

Reglas de diseno:
- Sin DAX: no se declaran medidas; toda agregacion es implicita (Function).
- Sin KPI: los indicadores son tarjetas (card).
- Sin visuales de Python: no son viables en DirectQuery.

CORRECCIONES DE FONDO (ver README):
- Cada tabla del modelo lleva SU PROPIO filtro de simulacion en la definicion
  del visual. El filtro de pagina NO sirve: al no haber relaciones entre las
  tablas, solo alcanza a la tabla por la que filtra. Ese era el motivo de que
  las tablas mostraran la suma de las 4 simulaciones (2115 salidas, 868
  superaciones, 529 excesos) mientras las tarjetas daban 1007.
- Los maximos se agregan con MAX, no con SUM (el "40,43 mil" era la suma de
  los maximos por grupo).
- D6 se filtra por `note = 'Con superaciones'` para no mostrar filas vacias.

PAGINA 2 (patrones temporales):
Se reconstruye entera sobre UNA SOLA tabla, D10_salidas_detalle (grano de
vuelo). Es la unica forma de que el segmentador de franja horaria filtre de
verdad a todos los visuales: con varias tablas preagregadas y sin relaciones,
un slicer solo alcanza a su propia tabla. Toda la pagina comparte D10, salvo
la comparativa por tipo de dia, que va a nivel de periodo y lo dice en su
subtitulo (ver README).
"""

import hashlib
import json
import pathlib
import shutil

DESTINO = pathlib.Path("/home/pablo/backend_aeroflow/powerbi")
REPORT = DESTINO / "AeroFlow.Report"
PAGES = REPORT / "definition" / "pages"

SIM = "SIM-01"

# --- tablas y sus columnas (tipos de Dremio) ---
TABLAS = {
    "D1_salidas_por_puerta_destino": [
        ("simulation_id", "string"), ("gate_id", "string"), ("terminal_id", "string"),
        ("destination_id", "string"), ("valid_departures", "int64"),
        ("distinct_aircraft", "int64")],
    "D2_pct_sobre_umbral_puerta": [
        ("simulation_id", "string"), ("gate_id", "string"), ("terminal_id", "string"),
        ("gate_threshold", "int64"), ("valid_departures", "int64"),
        ("over_threshold", "int64"), ("pct_over_threshold", "double")],
    # D4 ampliada para la pagina 2: dias incluidos, media diaria y % del total
    # se calculan en SQL (Dremio admite ventanas sobre agregados), no en DAX.
    "D4_laborables_fin_semana": [
        ("simulation_id", "string"), ("day_type", "string"),
        ("day_type_orden", "int64"), ("valid_departures", "int64"),
        ("days_included", "int64"), ("avg_departures_per_day", "double"),
        ("distinct_aircraft", "int64"), ("over_threshold", "int64"),
        ("pct_over_threshold", "double"), ("pct_of_total", "double")],
    # D10: proyeccion de V0_salidas a grano de vuelo para la pagina 2.
    # `salidas` (=1 por fila) permite contar vuelos con SUM, sin depender de
    # agregaciones que el motor pueda no resolver en DirectQuery.
    # `pct_superacion` es el indicador 0/1 con formato de porcentaje: su media
    # es exactamente la tasa de supervision, sin DAX.
    "D10_salidas_detalle": [
        ("simulation_id", "string"), ("event_id", "string"),
        ("scheduled_local_date", "date"), ("day_type", "string"),
        ("time_band", "string"), ("time_band_orden", "int64"),
        ("salidas", "int64"), ("supera_umbral", "int64"),
        ("pct_superacion", "double")],
    "D5_companias": [
        ("simulation_id", "string"), ("airline", "string"), ("valid_departures", "int64"),
        ("over_threshold", "int64"), ("pct_over_threshold", "double"),
        ("meets_minimum", "boolean")],
    "D5b_companias_por_puerta": [
        ("simulation_id", "string"), ("airline", "string"), ("gate_id", "string"),
        ("valid_departures", "int64"), ("over_threshold", "int64"),
        ("pct_over_threshold", "double")],
    "D6_retraso_medio_magnitud": [
        ("simulation_id", "string"), ("gate_id", "string"), ("terminal_id", "string"),
        ("destination_id", "string"), ("valid_departures", "int64"),
        ("avg_delay_minutes", "double"), ("over_threshold", "int64"),
        ("avg_minutes_over", "double"), ("max_minutes_over", "double"),
        ("note", "string")],
    "D7_aviones_repetidos_dia": [
        ("simulation_id", "string"), ("aircraft_id", "string"),
        ("scheduled_local_date", "date"), ("operations", "int64"),
        ("over_threshold_departures", "int64"), ("max_minutes_over", "double")],
    "D8_compania_modelo": [
        ("simulation_id", "string"), ("airline", "string"), ("aircraft_model", "string"),
        ("valid_departures", "int64"), ("over_threshold", "int64"),
        ("pct_over_threshold", "double"), ("meets_minimum", "boolean")],
    "D9_aviones_con_superacion": [
        ("simulation_id", "string"), ("valid_departures", "int64"),
        ("distinct_aircraft", "int64"), ("aircraft_with_exceedance", "int64"),
        ("over_threshold_departures", "int64"),
        ("pct_aircraft_with_exceedance", "double"),
        ("pct_departures_over_threshold", "double")],
}

# Columnas de orden: la columna visible se ordena por esta (sortByColumn).
# Es la forma sin DAX de que franjas y tipos de dia salgan en orden
# cronologico/logico tanto en graficos como en segmentadores.
ORDENAR_POR = {
    "D10_salidas_detalle": {"time_band": "time_band_orden"},
    "D4_laborables_fin_semana": {"day_type": "day_type_orden"},
}

# Funciones de agregacion implicitas (enum QueryAggregateFunction de PBIR).
SUMA, MEDIA, DISTINTOS, MINIMO, MAXIMO, CONTAR = 0, 1, 2, 3, 4, 5
DESCENDENTE, ASCENDENTE = "Descending", "Ascending"


def st(texto):
    return {"Value": texto}


def lit(texto):
    return {"expr": {"Literal": st(texto)}}


def col(entidad, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entidad}},
                       "Property": prop}}


def proy_columna(entidad, prop, etiqueta=None):
    return {"field": col(entidad, prop),
            "queryRef": f"{entidad}.{prop}",
            "nativeQueryRef": etiqueta or prop}


NOMBRE_FUNCION = {SUMA: "Sum", MEDIA: "Avg", DISTINTOS: "CountDistinct",
                  MINIMO: "Min", MAXIMO: "Max", CONTAR: "Count"}


def proy_agregada(entidad, prop, funcion=SUMA, etiqueta=None):
    etiqueta = etiqueta or prop
    return {"field": {"Aggregation": {
                "Expression": col(entidad, prop),
                "Function": funcion}},
            "queryRef": f"{NOMBRE_FUNCION[funcion]}({entidad}.{prop})",
            "nativeQueryRef": etiqueta}


def filtro_simulacion(entidad, sufijo):
    """Filtro categorico: entidad[simulation_id] IN (SIM-01).

    El valor de texto va entre comillas simples DENTRO del literal
    ("'SIM-01'"), que es la forma que produce el codificador de PBIR. Sin esas
    comillas el motor intenta interpretarlo como identificador y la
    representacion falla con un TypeError en SQExprValidationVisitor.
    """
    nombre = hashlib.sha1(f"filtro-{sufijo}".encode()).hexdigest()[:20]
    return {
        "name": nombre,
        "field": col(entidad, "simulation_id"),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": entidad, "Type": 0}],
            "Where": [{
                "Condition": {"In": {
                    "Expressions": [{"Column": {
                        "Expression": {"SourceRef": {"Source": "t"}},
                        "Property": "simulation_id"}}],
                    "Values": [[{"Literal": st(f"'{SIM}'")}]],
                }}
            }],
        },
        "howCreated": "User",
    }


def filtro_igualdad(entidad, campo, valor, sufijo):
    """Filtro categorico de igualdad sobre un campo de texto."""
    nombre = hashlib.sha1(f"filtro-{sufijo}".encode()).hexdigest()[:20]
    return {
        "name": nombre,
        "field": col(entidad, campo),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": entidad, "Type": 0}],
            "Where": [{
                "Condition": {"In": {
                    "Expressions": [{"Column": {
                        "Expression": {"SourceRef": {"Source": "t"}},
                        "Property": campo}}],
                    "Values": [[{"Literal": st(f"'{valor}'")}]],
                }}
            }],
        },
        "howCreated": "User",
    }


def visual(nombre, tipo, x, y, ancho, alto, roles, titulo=None, z=0,
           filtros=None, orden=None, objetos=None, subtitulo=None):
    """Crea un visual.

    `filtros` van en el propio visual (no de pagina): sin relaciones en el
    modelo, un filtro de pagina no alcanza a otras tablas.

    Las tarjetas (card) ocultan la etiqueta automatica de agregacion
    (`Suma de valid_departures`): con nombres de campo largos se sale del
    cuadro y ademas es ruido, porque el titulo ya dice que se mide. En su
    lugar el valor se muestra grande y en negrita.
    """
    v = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.5.0/schema.json",
        "name": nombre,
        "position": {"x": x, "y": y, "z": z, "width": ancho, "height": alto,
                     "tabOrder": z},
        "visual": {
            "visualType": tipo,
            "query": {"queryState": {
                rol: {"projections": proys} for rol, proys in roles.items()}},
            "drillFilterOtherVisuals": True,
        },
    }
    objetos = dict(objetos or {})
    if tipo == "card":
        objetos.setdefault("categoryLabels", [{"properties": {
            "show": lit("false")}}])
        objetos.setdefault("labels", [{"properties": {
            "fontSize": lit("32D"), "bold": lit("true")}}])
    if objetos:
        v["visual"]["objects"] = objetos

    vco = {}
    if titulo:
        vco["title"] = [{"properties": {
            "show": lit("true"),
            "text": lit("'" + titulo + "'"),
            "fontSize": lit("11D"),
        }}]
    if subtitulo:
        vco["subTitle"] = [{"properties": {
            "show": lit("true"),
            "text": lit("'" + subtitulo + "'"),
            "fontSize": lit("8D"),
            "italic": lit("true"),
        }}]
    if vco:
        v["visual"]["visualContainerObjects"] = vco

    if orden:
        campo, direccion = orden
        # sortDefinition espera la expresion desnuda, no la proyeccion
        expr = campo["field"] if "field" in campo else campo
        v["visual"]["query"]["sortDefinition"] = {"sort": [{
            "field": expr,
            "direction": direccion}], "isDefaultSort": False}
    if filtros:
        v["filterConfig"] = {"filters": filtros}
    return v


def filtros_tabla(entidad, sufijo, extra=None):
    """Filtro de simulacion (obligatorio) + filtros adicionales de esa tabla."""
    fs = [filtro_simulacion(entidad, f"{sufijo}-sim")]
    if extra:
        fs.extend(extra)
    return fs


def slicer(nombre, entidad, campo, x, y, ancho, alto, sufijo, titulo,
           seleccionar_todo=True):
    """Segmentacion por un campo de la propia tabla.

    Sin relaciones en el modelo, un slicer solo filtra los visuales que usan
    SU MISMA tabla. Por eso en la pagina 2 todos los visuales comparten D10.

    `selectAllCheckboxEnabled` anade la casilla «Seleccionar todo», que es la
    forma de limpiar el filtro de golpe. El texto se ajusta (`textWrap`) para
    que los nombres largos de franja no se corten.
    """
    objetos = {
        "selection": [{"properties": {
            "selectAllCheckboxEnabled": lit("true" if seleccionar_todo else "false"),
            "singleSelect": lit("false"),
        }}],
        "value": [{"properties": {
            "fontSize": lit("9D"),
            "textWrap": lit("true"),
        }}],
    }
    return visual(nombre, "listSlicer", x, y, ancho, alto,
                  {"Values": [proy_columna(entidad, campo)]}, titulo, z=9,
                  filtros=filtros_tabla(entidad, f"{sufijo}-sl"),
                  objetos=objetos)


def caja_texto(nombre, x, y, ancho, alto, lineas, titulo=None, z=0, tamano=9):
    """Caja de texto estatica.

    Sirve para el esquema del aeropuerto: la memoria dice que el esquema puede
    elaborarlo el alumnado y que NO hace falta un mapa geografico. Los
    parrafos van en objects.general (forma que produce Power BI Desktop); el
    contenido es literal, no consulta, asi que no lleva filtro ni roles.
    """
    v = visual(nombre, "textbox", x, y, ancho, alto, {}, titulo, z=z)
    v["visual"]["objects"] = {
        "text": [{"properties": {"fontSize": lit(f"{tamano}D")}}],
        "general": [{"properties": {"paragraphs": [
            {"textRuns": [{"value": linea}]} for linea in lineas]}}],
    }
    return v


# --- formato comun de ejes (evita etiquetas cortadas y escalas enganosas) ---
def eje_categoria(orientacion_vertical=False, tamano=8, invertir=None):
    props = {
        "show": lit("true"),
        "fontSize": lit(f"{tamano}D"),
        "showAxisTitle": lit("false"),
    }
    if invertir is not None:
        props["invertAxis"] = lit("true" if invertir else "false")
    return {"categoryAxis": [{"properties": props}]}


def eje_valor(desde_cero=True, titulo=None, tamano=8):
    props = {"show": lit("true"), "fontSize": lit(f"{tamano}D")}
    if desde_cero:
        props["start"] = lit("0D")
    if titulo:
        props["showAxisTitle"] = lit("true")
        props["titleText"] = lit("'" + titulo + "'")
        props["titleFontSize"] = lit("8D")
    else:
        props["showAxisTitle"] = lit("false")
    return {"valueAxis": [{"properties": props}]}


def etiquetas_datos(mostrar=True, tamano=8, formato=None, precision=0):
    props = {"show": lit("true" if mostrar else "false"),
             "fontSize": lit(f"{tamano}D"),
             "labelPrecision": lit(f"{precision}L")}
    if formato:
        props["valueCustomFormatString"] = lit("'" + formato + "'")
    return {"labels": [{"properties": props}]}


D9 = "D9_aviones_con_superacion"
D2 = "D2_pct_sobre_umbral_puerta"
D4 = "D4_laborables_fin_semana"
D5 = "D5_companias"
D5b = "D5b_companias_por_puerta"
D6 = "D6_retraso_medio_magnitud"
D7 = "D7_aviones_repetidos_dia"
D8 = "D8_compania_modelo"
D10 = "D10_salidas_detalle"

# ============================ PAGINA 1 ============================
# Estado general: 4 tarjetas D9 + barras por puerta (D2), ordenadas.
p1 = [
    # --- banda superior: 6 tarjetas ------------------------------------
    # "Volumen" son las 4 de recuento; "proporcion" son las 2 de
    # porcentaje. No se funden en una tarjeta porque miden conceptos
    # distintos: 37,14 % de las SALIDAS superan el umbral, mientras que el
    # 100 % de los AVIONES registran al menos una superacion. Es la
    # diferencia que la memoria pide comparar explicitamente.
    visual("p1c1", "card", 20, 20, 195, 130,
           {"Values": [proy_agregada(D9, "valid_departures", SUMA)]},
           "Salidas válidas", z=0,
           filtros=filtros_tabla(D9, "p1c1")),
    visual("p1c2", "card", 223, 20, 195, 130,
           {"Values": [proy_agregada(D9, "over_threshold_departures", SUMA)]},
           "Superaciones", z=0,
           filtros=filtros_tabla(D9, "p1c2")),
    visual("p1c3", "card", 426, 20, 195, 130,
           {"Values": [proy_agregada(D9, "distinct_aircraft", SUMA)]},
           "Aviones distintos", z=0,
           filtros=filtros_tabla(D9, "p1c3")),
    visual("p1c4", "card", 629, 20, 195, 130,
           {"Values": [proy_agregada(D9, "aircraft_with_exceedance", SUMA)]},
           "Aviones con exceso", z=0,
           filtros=filtros_tabla(D9, "p1c4")),
    visual("p1c5", "card", 832, 20, 210, 130,
           {"Values": [proy_agregada(D9, "pct_departures_over_threshold",
                                     MAXIMO, "% de salidas con exceso")]},
           "% de salidas que superan", z=0,
           filtros=filtros_tabla(D9, "p1c5")),
    visual("p1c6", "card", 1050, 20, 210, 130,
           {"Values": [proy_agregada(D9, "pct_aircraft_with_exceedance",
                                     MAXIMO, "% de aviones con exceso")]},
           "% de aviones con exceso", z=0,
           filtros=filtros_tabla(D9, "p1c6")),

    # --- filtro de puerta (afecta a los dos graficos) -------------------
    slicer("p1s1", D2, "gate_id", 20, 175, 180, 525, "p1s1", "Puerta"),

    # --- esquema de las cinco puertas -----------------------------------
    # La memoria admite un esquema propio y NO exige mapa. Es referencia
    # estatica: no filtra (para eso esta el segmentador) y no consulta
    # Dremio. La organizacion fisica (una puerta por terminal) y los
    # umbrales son datos de configuracion, no metricas.
    caja_texto("p1e0", 215, 175, 345, 68,
               ["Cinco terminales (T1-T5), una puerta por terminal (G1-G5).",
                "Umbral de retraso: 15 min en T1, T2, T3 y T5; 20 min en T4."],
               "Esquema del aeropuerto", z=1, tamano=8),
    caja_texto("p1e1", 235, 251, 130, 56,
               ["G1", "Terminal T1 · umbral 15 min"], z=2, tamano=8),
    caja_texto("p1e2", 375, 251, 130, 56,
               ["G2", "Terminal T2 · umbral 15 min"], z=2, tamano=8),
    caja_texto("p1e3", 235, 315, 130, 56,
               ["G3", "Terminal T3 · umbral 15 min"], z=2, tamano=8),
    caja_texto("p1e4", 375, 315, 130, 56,
               ["G4", "Terminal T4 · umbral 20 min"], z=2, tamano=8),
    caja_texto("p1e5", 305, 379, 130, 56,
               ["G5", "Terminal T5 · umbral 15 min"], z=2, tamano=8),

    # --- barras por puerta ----------------------------------------------
    # Recuento y porcentaje en graficos separados, como en la pagina 2.
    # Ambos ordenados por superaciones absolutas, que en SIM-01 dan el mismo
    # orden que el porcentaje (G4 128 y 62,1 % primero; G5 35 y 25,5 %
    # ultimo), asi que las dos columnas se leen en paralelo.
    visual("p1b1", "clusteredBarChart", 215, 448, 345, 252,
           {"Category": [proy_columna(D2, "gate_id")],
            "Y": [proy_agregada(D2, "over_threshold", SUMA)]},
           "Superaciones por puerta", z=3,
           filtros=filtros_tabla(D2, "p1b1"),
           orden=(proy_agregada(D2, "over_threshold", SUMA), DESCENDENTE)),
    visual("p1b2", "clusteredBarChart", 575, 175, 685, 525,
           {"Category": [proy_columna(D2, "gate_id")],
            "Y": [proy_agregada(D2, "pct_over_threshold", MAXIMO,
                                "% de salidas que superan el umbral")]},
           "% de salidas que superan el umbral, por puerta", z=4,
           filtros=filtros_tabla(D2, "p1b2"),
           orden=(proy_agregada(D2, "over_threshold", SUMA), DESCENDENTE)),
]

# ============================ PAGINA 2 ============================
# Patrones temporales. TODA la pagina usa D10_salidas_detalle, de modo que el
# segmentador de franja horaria filtre de forma coherente tarjetas, evolucion
# y ambos graficos de franja.
p2 = [
    # --- banda superior: segmentador + tarjetas ------------------------
    slicer("p2s1", D10, "time_band", 20, 20, 196, 152, "p2s1",
           "Franja horaria"),

    visual("p2c1", "card", 224, 20, 250, 152,
           {"Values": [proy_agregada(D10, "salidas", SUMA, "Salidas válidas")]},
           "Salidas válidas", z=0,
           filtros=filtros_tabla(D10, "p2c1")),
    visual("p2c2", "card", 483, 20, 250, 152,
           {"Values": [proy_agregada(D10, "supera_umbral", SUMA, "Superaciones")]},
           "Superaciones", z=0,
           filtros=filtros_tabla(D10, "p2c2")),
    visual("p2c3", "card", 742, 20, 250, 152,
           {"Values": [proy_agregada(D10, "pct_superacion", MEDIA,
                                     "Tasa de superación")]},
           "Tasa de superación", z=0,
           filtros=filtros_tabla(D10, "p2c3")),
    visual("p2c4", "card", 1001, 20, 250, 152,
           {"Values": [proy_agregada(D10, "scheduled_local_date", DISTINTOS,
                                     "Días con actividad")]},
           "Días con actividad", z=0,
           filtros=filtros_tabla(D10, "p2c4")),

    # --- evolucion diaria: dos series en el MISMO eje ------------------
    # Mismo eje a proposito: ambas series son recuentos de vuelos, asi que
    # compartir escala no distorsiona la comparacion (un eje secundario si
    # lo haria). Interpolacion lineal y marcadores: nada de curvas suaves
    # que inventen tendencias entre fechas.
    visual("p2l1", "lineChart", 20, 180, 810, 250,
           {"Category": [proy_columna(D10, "scheduled_local_date")],
            "Y": [proy_agregada(D10, "salidas", SUMA, "Salidas válidas"),
                  proy_agregada(D10, "supera_umbral", SUMA, "Superaciones")]},
           "Evolución diaria: salidas y superaciones", z=1,
           filtros=filtros_tabla(D10, "p2l1"),
           objetos={
               "lineStyles": [{"properties": {
                   "lineChartType": lit("'linear'"),
                   "showMarker": lit("true"),
                   "markerShape": lit("'circle'"),
                   "markerSize": lit("5D"),
               }}],
               "labels": [{"properties": {
                   "show": lit("true"),
                   "fontSize": lit("8D"),
                   "labelPrecision": lit("0L"),
                   # si dos etiquetas chocan, se oculta una en vez de solaparse
                   "optimizeLabelDisplay": lit("true"),
               }}],
               "legend": [{"properties": {
                   "show": lit("true"),
                   "position": lit("'BottomCenter'"),
                   "fontSize": lit("8D"),
               }}],
               **eje_categoria(tamano=8),
               **eje_valor(desde_cero=True, titulo="Vuelos"),
           }),

    # --- superaciones por franja: absoluto -----------------------------
    # Barras horizontales: los nombres largos de franja caben enteros y el
    # orden es cronologico (Madrugada arriba) gracias a sortByColumn.
    visual("p2b1", "clusteredBarChart", 838, 180, 422, 250,
           {"Category": [proy_columna(D10, "time_band")],
            "Y": [proy_agregada(D10, "supera_umbral", SUMA, "Superaciones")]},
           "Superaciones por franja horaria", z=2,
           filtros=filtros_tabla(D10, "p2b1"),
           objetos={
               **eje_categoria(tamano=8, invertir=True),
               **eje_valor(desde_cero=True, titulo="Superaciones"),
               **etiquetas_datos(tamano=8),
               "legend": [{"properties": {"show": lit("false")}}],
           }),

    # --- tasa por franja: relativo -------------------------------------
    # Media de una columna 0/1 con formato de porcentaje = tasa exacta.
    # Va en visual aparte para no mezclar recuento absoluto con porcentaje
    # en el mismo eje.
    visual("p2b2", "clusteredBarChart", 20, 438, 400, 262,
           {"Category": [proy_columna(D10, "time_band")],
            "Y": [proy_agregada(D10, "pct_superacion", MEDIA,
                                "Tasa de superación")]},
           "Tasa de superación por franja", z=3,
           filtros=filtros_tabla(D10, "p2b2"),
           objetos={
               **eje_categoria(tamano=8, invertir=True),
               **eje_valor(desde_cero=True, titulo="% de salidas"),
               **etiquetas_datos(tamano=8, formato="0.0%", precision=1),
               "legend": [{"properties": {"show": lit("false")}}],
           }),

    # --- comparativa por tipo de dia: a nivel de periodo ---------------
    # D4 trae una fila por tipo de dia con dias incluidos, media diaria y
    # % del total ya calculados en SQL. Como cada grupo tiene UNA sola fila,
    # agregar con SUMA devuelve el valor de la fila (no suma filas entre si).
    # Sin fila de totales: la media diaria y la tasa no son aditivas y un
    # total las falsearia; los totales correctos estan en las tarjetas.
    visual("p2t1", "tableEx", 428, 438, 832, 262,
           {"Values": [
               proy_columna(D4, "day_type", "Tipo de día"),
               proy_agregada(D4, "valid_departures", SUMA, "Salidas"),
               proy_agregada(D4, "days_included", SUMA, "Días"),
               proy_agregada(D4, "avg_departures_per_day", SUMA, "Media diaria"),
               proy_agregada(D4, "pct_of_total", SUMA, "% del total"),
               proy_agregada(D4, "pct_over_threshold", SUMA,
                             "Tasa de superación")]},
           "Comparativa por tipo de día", z=4,
           subtitulo="Periodo completo (no depende del filtro de franja)",
           filtros=filtros_tabla(D4, "p2t1"),
           objetos={
               "columnHeaders": [{"properties": {
                   "fontSize": lit("8D"), "bold": lit("true"),
                   "wordWrap": lit("true"),
                   "autoSizeColumnWidth": lit("true"),
               }}],
               "values": [{"properties": {
                   "fontSize": lit("9D"), "wordWrap": lit("false"),
               }}],
               "grid": [{"properties": {
                   "gridVertical": lit("false"),
                   "rowPadding": lit("2L"),
               }}],
               "total": [{"properties": {"totals": lit("false")}}],
           }),
]

# ============================ PAGINA 3 ============================
# La tabla puerta-destino se filtra ademas por note, para no mostrar filas
# sin superaciones (que solo anaden ruido a la lectura).
p3 = [
    visual("p3c1", "card", 20, 20, 290, 120,
           {"Values": [proy_agregada(D5, "valid_departures", SUMA)]},
           "Salidas válidas (por compañía)", z=0,
           filtros=filtros_tabla(D5, "p3c1")),
    visual("p3c2", "card", 325, 20, 290, 120,
           {"Values": [proy_agregada(D5, "over_threshold", SUMA)]},
           "Superaciones (por compañía)", z=0,
           filtros=filtros_tabla(D5, "p3c2")),
    visual("p3c3", "card", 630, 20, 290, 120,
           {"Values": [proy_agregada(D8, "valid_departures", SUMA)]},
           "Salidas válidas (por modelo)", z=0,
           filtros=filtros_tabla(D8, "p3c3")),
    visual("p3c4", "card", 935, 20, 325, 120,
           {"Values": [proy_agregada(D7, "max_minutes_over", MAXIMO)]},
           "Exceso máximo (minutos)", z=0,
           filtros=filtros_tabla(D7, "p3c4")),

    # Barras horizontales, ordenadas de mayor a menor, con etiquetas de datos.
    slicer("p3s1", D5, "airline", 20, 160, 165, 260, "p3s1", "Compañía"),

    visual("p3b1", "clusteredBarChart", 200, 160, 430, 260,
           {"Category": [proy_columna(D5, "airline")],
            "Y": [proy_agregada(D5, "over_threshold", SUMA)]},
           "Superaciones por compañía (mayor a menor)", z=1,
           filtros=filtros_tabla(D5, "p3b1"),
           orden=(proy_agregada(D5, "over_threshold", SUMA), DESCENDENTE)),
    visual("p3b2", "clusteredBarChart", 650, 160, 610, 260,
           {"Category": [proy_columna(D8, "aircraft_model")],
            "Y": [proy_agregada(D8, "valid_departures", SUMA)]},
           "Salidas por modelo de avión (mayor a menor)", z=2,
           filtros=filtros_tabla(D8, "p3b2"),
           orden=(proy_agregada(D8, "valid_departures", SUMA), DESCENDENTE)),
    visual("p3b3", "clusteredBarChart", 20, 440, 610, 260,
           {"Category": [proy_columna(D5b, "gate_id")],
            "Y": [proy_agregada(D5b, "over_threshold", SUMA)]},
           "Superaciones por puerta", z=3,
           filtros=filtros_tabla(D5b, "p3b3"),
           orden=(proy_agregada(D5b, "over_threshold", SUMA), DESCENDENTE)),
    visual("p3t1", "tableEx", 650, 440, 610, 260,
           {"Values": [
               proy_columna(D6, "gate_id", "Puerta"),
               proy_columna(D6, "destination_id", "Destino"),
               proy_agregada(D6, "valid_departures", SUMA, "Salidas"),
               proy_agregada(D6, "over_threshold", SUMA, "Superan"),
               proy_agregada(D6, "avg_minutes_over", MEDIA, "Exceso medio")]},
           "Puerta y destino con superaciones", z=4,
           filtros=filtros_tabla(D6, "p3t1", extra=[
               filtro_igualdad(D6, "note", "Con superaciones", "p3t1-note")]),
           orden=(proy_agregada(D6, "over_threshold", SUMA), DESCENDENTE)),
]


def formato_columna(nombre, tipo):
    """Formato de presentacion por columna.

    Dos escalas de porcentaje conviven en las vistas y se distinguen por
    nombre de columna:

    - `pct_superacion` (D10) es un INDICADOR 0/1 en coma flotante. Su formato
      es de tanto por ciento ("0.0%"), que multiplica por 100 al mostrar: la
      media 0.3714 se lee 37,1 %.

    - El resto de `pct_*` (D2, D4, D5, D8, D9) ya va multiplicado por 100 en
      SQL (35.92 = 35,92 %). Con "0.0%" Power BI volveria a multiplicar y
      mostraria 3592 %, asi que llevan formato de numero con un "%" literal
      anadido: 35,92 %.

    La regla NO es "pct_ = porcentaje", sino mirar la escala de cada columna.
    """
    if nombre == "scheduled_local_date" and tipo == "date":
        # eje de la evolucion: "05/10", no "05/10/2026 0:00:00"
        return "dd/MM"
    if nombre == "pct_superacion":
        # indicador 0/1: el formato % multiplica por 100 al mostrar
        return "0.0%"
    if nombre.startswith("pct_"):
        # ya va multiplicado por 100 en SQL: solo se anade el signo literal
        return '#,##0.0"%"'
    if nombre.startswith("avg_"):
        return "#,##0.0"
    if tipo == "double":
        return "#,##0.00"
    if tipo == "int64":
        return "#,##0"
    return None


def escribir_modelo():
    tablas_dir = DESTINO / "AeroFlow.SemanticModel" / "definition" / "tables"
    tablas_dir.mkdir(parents=True, exist_ok=True)

    def tmdl_tipo(t):
        return {"string": "string", "int64": "int64", "double": "double",
                "boolean": "boolean", "date": "dateTime"}[t]

    for tabla, cols in TABLAS.items():
        lineas = [f"table {tabla}", ""]
        for nombre, tipo in cols:
            lineas.append(f"\tcolumn {nombre}")
            lineas.append(f"\t\tdataType: {tmdl_tipo(tipo)}")
            fmt = formato_columna(nombre, tipo)
            if fmt:
                lineas.append(f"\t\tformatString: {fmt}")
            # porcentajes, medias y maximos no se suman nunca
            no_sumar = nombre.startswith(("pct_", "avg_", "max_"))
            if (tipo in ("string", "boolean", "date") or no_sumar
                    or nombre.endswith("_orden")):
                lineas.append("\t\tsummarizeBy: none")
            else:
                lineas.append("\t\tsummarizeBy: sum")
            lineas.append(f"\t\tsourceColumn: {nombre}")
            orden = ORDENAR_POR.get(tabla, {}).get(nombre)
            if orden:
                lineas.append(f"\t\tsortByColumn: {orden}")
            lineas.append("")
        lineas += [
            f"\tpartition {tabla} = m",
            "\t\tmode: directQuery",
            "\t\tsource =",
            "\t\t\tlet",
            '\t\t\t\tOrigen = Dremio.DatabasesV370("adbc://192.168.0.26:32010", "Disabled"),',
            '\t\t\t\tAeroflow = Origen{[Name="Aeroflow",Kind="Schema"]}[Data],',
            f'\t\t\t\tVista = Aeroflow{{[Name="{tabla}",Kind="Table"]}}[Data]',
            "\t\t\tin",
            "\t\t\t\tVista",
            "",
        ]
        (tablas_dir / f"{tabla}.tmdl").write_text("\n".join(lineas), encoding="utf-8")

    # Limpiar ficheros de tablas retiradas del modelo
    for viejo in tablas_dir.glob("*.tmdl"):
        if viejo.stem not in TABLAS:
            viejo.unlink()

    refs = "\n".join(f"ref table {t}" for t in TABLAS)
    (DESTINO / "AeroFlow.SemanticModel" / "definition" / "model.tmdl").write_text(
        "model Model\n"
        "\tculture: es-ES\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: es-ES\n\n"
        f"{refs}\n", encoding="utf-8")


def main():
    shutil.rmtree(PAGES, ignore_errors=True)
    PAGES.mkdir(parents=True)

    escribir_modelo()

    paginas = [
        ("a1000000000000000000000000000001", "Estado general", p1),
        ("a2000000000000000000000000000002", "Patrones temporales", p2),
        ("a3000000000000000000000000000003", "Companias y aviones", p3),
    ]

    orden = []
    for pid, nombre, visuales in paginas:
        orden.append(pid)
        d = PAGES / pid
        d.mkdir(parents=True)
        meta = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": pid,
            "displayName": nombre,
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
        }
        (d / "page.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
        vdir = d / "visuals"
        vdir.mkdir()
        for v in visuales:
            sub = vdir / v["name"]
            sub.mkdir()
            (sub / "visual.json").write_text(
                json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")

    (PAGES / "pages.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
        "pageOrder": orden,
        "activePageName": orden[0],
    }, indent=2), encoding="utf-8")

    total = sum(len(v) for _, _, v in paginas)
    print(f"paginas: {len(paginas)}, visuales: {total}")


if __name__ == "__main__":
    main()
