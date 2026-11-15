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
    "D3_horas_franjas": [
        ("simulation_id", "string"), ("gate_id", "string"), ("local_hour", "int64"),
        ("time_band", "string"), ("valid_departures", "int64"),
        ("over_threshold", "int64"), ("pct_over_threshold", "double")],
    "D4_laborables_fin_semana": [
        ("simulation_id", "string"), ("day_type", "string"), ("valid_departures", "int64"),
        ("distinct_aircraft", "int64"), ("over_threshold", "int64"),
        ("pct_over_threshold", "double")],
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
    "D4b_evolucion_diaria": [
        ("simulation_id", "string"), ("scheduled_local_date", "date"),
        ("day_type", "string"), ("valid_departures", "int64"),
        ("distinct_aircraft", "int64"), ("over_threshold", "int64"),
        ("pct_over_threshold", "double")],
    "D9_aviones_con_superacion": [
        ("simulation_id", "string"), ("valid_departures", "int64"),
        ("distinct_aircraft", "int64"), ("aircraft_with_exceedance", "int64"),
        ("over_threshold_departures", "int64"),
        ("pct_aircraft_with_exceedance", "double"),
        ("pct_departures_over_threshold", "double")],
}

SUMA, MEDIA, DISTINTOS, MINIMO, MAXIMO = 0, 1, 2, 3, 4
DESCENDENTE, ASCENDENTE = "Descending", "Ascending"


def st(texto):
    return {"Value": texto}


def col(entidad, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entidad}},
                       "Property": prop}}


def proy_columna(entidad, prop, etiqueta=None):
    return {"field": col(entidad, prop),
            "queryRef": f"{entidad}.{prop}",
            "nativeQueryRef": etiqueta or prop}


NOMBRE_FUNCION = {SUMA: "Sum", MEDIA: "Avg", DISTINTOS: "Count", MINIMO: "Min",
                  MAXIMO: "Max"}


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
           filtros=None, orden=None):
    """Crea un visual. `filtros` van en el propio visual (no de pagina).

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
    if tipo == "card":
        v["visual"]["objects"] = {
            "categoryLabels": [{"properties": {
                "show": {"expr": {"Literal": st("false")}},
            }}],
            "labels": [{"properties": {
                "fontSize": {"expr": {"Literal": st("32D")}},
                "bold": {"expr": {"Literal": st("true")}},
            }}],
        }
    if titulo:
        v["visual"]["visualContainerObjects"] = {"title": [{"properties": {
            "show": {"expr": {"Literal": st("true")}},
            "text": {"expr": {"Literal": st("'" + titulo + "'")}},
            "fontSize": {"expr": {"Literal": st("11D")}},
        }}]}
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


def slicer(nombre, entidad, campo, x, y, ancho, alto, sufijo, titulo):
    """Segmentacion por un campo de la propia tabla.

    Sin relaciones en el modelo, un slicer solo filtra los visuales que usan
    SU MISMA tabla. Se colocan en columna vertical, donde si comparten tabla.
    """
    v = visual(nombre, "listSlicer", x, y, ancho, alto,
               {"Values": [proy_columna(entidad, campo)]}, titulo, z=9,
               filtros=filtros_tabla(entidad, f"{sufijo}-sl"))
    return v


D9 = "D9_aviones_con_superacion"
D2 = "D2_pct_sobre_umbral_puerta"
D3 = "D3_horas_franjas"
D4 = "D4_laborables_fin_semana"
D4b = "D4b_evolucion_diaria"
D5 = "D5_companias"
D5b = "D5b_companias_por_puerta"
D6 = "D6_retraso_medio_magnitud"
D7 = "D7_aviones_repetidos_dia"
D8 = "D8_compania_modelo"

# ============================ PAGINA 1 ============================
# Estado general: 4 tarjetas D9 + barras por puerta (D2), ordenadas.
p1 = [
    visual("p1c1", "card", 20, 20, 290, 130,
           {"Values": [proy_agregada(D9, "valid_departures", SUMA)]},
           "Salidas válidas", z=0,
           filtros=filtros_tabla(D9, "p1c1")),
    visual("p1c2", "card", 325, 20, 290, 130,
           {"Values": [proy_agregada(D9, "over_threshold_departures", SUMA)]},
           "Superaciones del umbral", z=0,
           filtros=filtros_tabla(D9, "p1c2")),
    visual("p1c3", "card", 630, 20, 290, 130,
           {"Values": [proy_agregada(D9, "distinct_aircraft", SUMA)]},
           "Aviones distintos", z=0,
           filtros=filtros_tabla(D9, "p1c3")),
    visual("p1c4", "card", 935, 20, 325, 130,
           {"Values": [proy_agregada(D9, "aircraft_with_exceedance", SUMA)]},
           "Aviones con exceso", z=0,
           filtros=filtros_tabla(D9, "p1c4")),

    slicer("p1s1", D2, "gate_id", 20, 175, 180, 525, "p1s1", "Puerta"),

    visual("p1b1", "clusteredBarChart", 215, 175, 520, 525,
           {"Category": [proy_columna(D2, "gate_id")],
            "Y": [proy_agregada(D2, "over_threshold", SUMA)]},
           "Superaciones por puerta", z=1,
           filtros=filtros_tabla(D2, "p1b1"),
           orden=(proy_agregada(D2, "over_threshold", SUMA), DESCENDENTE)),
    visual("p1b2", "clusteredBarChart", 750, 175, 510, 525,
           {"Category": [proy_columna(D2, "valid_departures")],
            "Y": [proy_agregada(D2, "over_threshold", SUMA)]},
           "Superaciones frente a salidas por puerta", z=2,
           filtros=filtros_tabla(D2, "p1b2"),
           orden=(proy_agregada(D2, "over_threshold", SUMA), DESCENDENTE)),
]

# ============================ PAGINA 2 ============================
p2 = [
    visual("p2l1", "lineChart", 20, 20, 1240, 330,
           {"Category": [proy_columna(D4b, "scheduled_local_date")],
            "Y": [proy_agregada(D4b, "valid_departures", SUMA)]},
           "Evolución diaria de salidas válidas", z=0,
           filtros=filtros_tabla(D4b, "p2l1")),
    slicer("p2s1", D3, "time_band", 20, 370, 170, 330, "p2s1", "Franja"),

    visual("p2b1", "clusteredColumnChart", 205, 370, 425, 330,
           {"Category": [proy_columna(D3, "time_band")],
            "Y": [proy_agregada(D3, "over_threshold", SUMA)]},
           "Superaciones por franja horaria", z=1,
           filtros=filtros_tabla(D3, "p2b1"),
           orden=(proy_agregada(D3, "over_threshold", SUMA), DESCENDENTE)),
    visual("p2b2", "clusteredColumnChart", 650, 370, 610, 330,
           {"Category": [proy_columna(D4, "day_type")],
            "Y": [proy_agregada(D4, "valid_departures", SUMA)]},
           "Salidas por tipo de día", z=2,
           filtros=filtros_tabla(D4, "p2b2"),
           orden=(proy_agregada(D4, "valid_departures", SUMA), DESCENDENTE)),
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
            # porcentajes, medias y maximos no se suman nunca
            no_sumar = nombre.startswith(("pct_", "avg_", "max_"))
            if tipo == "double":
                lineas.append("\t\tformatString: #,##0.00")
            elif tipo == "int64" and nombre != "local_hour":
                lineas.append("\t\tformatString: #,##0")
            if tipo in ("string", "boolean", "date") or no_sumar or nombre == "local_hour":
                lineas.append("\t\tsummarizeBy: none")
            else:
                lineas.append("\t\tsummarizeBy: sum")
            lineas.append(f"\t\tsourceColumn: {nombre}")
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
