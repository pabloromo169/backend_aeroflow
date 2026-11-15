#!/usr/bin/env python3
"""Genera las 3 paginas del informe AeroFlow en formato PBIR.

Reglas de diseno:
- Sin DAX: no se declaran medidas; toda agregacion es implicita (Function).
- Sin KPI: los indicadores son tarjetas (card).
- Sin visuales de Python: no son viables en DirectQuery.
- Todas las paginas filtran simulation_id = SIM-01 con un filtro de pagina,
  asi ningun visual necesita filtros propios.
"""

import json
import pathlib
import shutil
import uuid

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
        ("avg_minutes_over", "double"), ("max_minutes_over", "double"), ("note", "string")],
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

SUMA, CONTAR = 0, 2  # QueryAggregateFunction: Sum, Count


def st(texto):
    return {"Value": texto}


def col(entidad, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entidad}},
                       "Property": prop}}


def proy_columna(entidad, prop):
    return {"field": col(entidad, prop),
            "queryRef": f"{entidad}.{prop}",
            "nativeQueryRef": prop}


def proy_agregada(entidad, prop, funcion=SUMA, etiqueta=None):
    etiqueta = etiqueta or prop
    return {"field": {"Aggregation": {
                "Expression": col(entidad, prop),
                "Function": funcion}},
            "queryRef": f"{'Sum' if funcion == SUMA else 'Count'}({entidad}.{prop})",
            "nativeQueryRef": etiqueta}


def visual(nombre, tipo, x, y, ancho, alto, roles, titulo, z=0):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.5.0/schema.json",
        "name": nombre,
        "position": {"x": x, "y": y, "z": z, "width": ancho, "height": alto,
                     "tabOrder": z},
        "visual": {
            "visualType": tipo,
            "query": {"queryState": {
                rol: {"projections": proys} for rol, proys in roles.items()}},
            "visualContainerObjects": {"title": [{"properties": {
                "show": {"expr": {"Literal": st("true")}},
                "text": {"expr": {"Literal": st("'" + titulo + "'")}},
            }}]} if titulo else {},
            "drillFilterOtherVisuals": True,
        },
    }


def filtro_simulacion(entidad="D9_aviones_con_superacion", sufijo="1"):
    """Filtro categorico: entidad[simulation_id] IN (SIM-01)."""
    return {
        "name": f"FiltroSimulacion_{sufijo}",
        "field": col(entidad, "simulation_id"),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "d", "Entity": entidad, "Type": 0}],
            "Where": [{
                "Condition": {"In": {
                    "Expressions": [{"Column": {
                        "Expression": {"SourceRef": {"Source": "d"}},
                        "Property": "simulation_id"}}],
                    "Values": [[{"Literal": st(SIM)}]],
                }}
            }],
        },
    }


def pagina(pid, nombre, visuales, filtro_entidad="D9_aviones_con_superacion",
           sufijo="1"):
    return pid, {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
        "name": pid,
        "displayName": nombre,
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
        "filterConfig": {"filters": [filtro_simulacion(filtro_entidad, sufijo)]},
    }, visuales


# ============================ PAGINA 1 ============================
D9 = "D9_aviones_con_superacion"
D2 = "D2_pct_sobre_umbral_puerta"

p1 = [
    visual("p1c1", "card", 20, 20, 240, 130,
           {"Values": [proy_agregada(D9, "valid_departures")]}, "Salidas validas"),
    visual("p1c2", "card", 275, 20, 240, 130,
           {"Values": [proy_agregada(D9, "distinct_aircraft")]}, "Aviones distintos"),
    visual("p1c3", "card", 530, 20, 240, 130,
           {"Values": [proy_agregada(D9, "over_threshold_departures")]}, "Superan umbral"),
    visual("p1c4", "card", 785, 20, 240, 130,
           {"Values": [proy_agregada(D9, "aircraft_with_exceedance")]}, "Aviones con exceso"),
    visual("p1c5", "card", 1040, 20, 220, 130,
           {"Values": [proy_agregada(D2, "over_threshold")]}, "Superaciones (D2)"),

    visual("p1b1", "clusteredBarChart", 20, 170, 620, 530,
           {"Category": [proy_columna(D2, "gate_id")],
            "Y": [proy_agregada(D2, "over_threshold")]},
           "Superaciones por puerta", z=1),
    visual("p1b2", "clusteredColumnChart", 660, 170, 600, 530,
           {"Category": [proy_columna(D2, "gate_id")],
            "Y": [proy_agregada(D2, "valid_departures")]},
           "Salidas validas por puerta", z=2),
]

# ============================ PAGINA 2 ============================
D3 = "D3_horas_franjas"
D4b = "D4b_evolucion_diaria"
D4 = "D4_laborables_fin_semana"
D6 = "D6_retraso_medio_magnitud"

p2 = [
    visual("p2l1", "lineChart", 20, 20, 1240, 330,
           {"Category": [proy_columna(D4b, "scheduled_local_date")],
            "Y": [proy_agregada(D4b, "valid_departures")]},
           "Evolucion diaria de salidas validas"),
    visual("p2b1", "clusteredColumnChart", 20, 370, 610, 330,
           {"Category": [proy_columna(D3, "time_band")],
            "Y": [proy_agregada(D3, "over_threshold")]},
           "Superaciones por franja horaria", z=1),
    visual("p2b2", "clusteredColumnChart", 650, 370, 610, 330,
           {"Category": [proy_columna(D4, "day_type")],
            "Y": [proy_agregada(D4, "valid_departures")]},
           "Salidas por tipo de dia", z=2),
]

# ============================ PAGINA 3 ============================
D5 = "D5_companias"
D5b = "D5b_companias_por_puerta"
D8 = "D8_compania_modelo"
D7 = "D7_aviones_repetidos_dia"

p3 = [
    visual("p3c1", "card", 20, 20, 240, 120,
           {"Values": [proy_agregada(D7, "over_threshold_departures")]},
           "Excesos de aviones reincidentes"),
    visual("p3c2", "card", 275, 20, 240, 120,
           {"Values": [proy_agregada(D7, "max_minutes_over")]},
           "Exceso maximo (min)"),
    visual("p3c3", "card", 530, 20, 240, 120,
           {"Values": [proy_agregada(D5, "valid_departures")]},
           "Salidas por compania (suma)"),
    visual("p3c4", "card", 785, 20, 240, 120,
           {"Values": [proy_agregada(D5b, "valid_departures")]},
           "Salidas por puerta y compania"),

    visual("p3b1", "clusteredBarChart", 20, 160, 610, 260,
           {"Category": [proy_columna(D5, "airline")],
            "Y": [proy_agregada(D5, "over_threshold")]},
           "Superaciones por compania", z=1),
    visual("p3b2", "clusteredBarChart", 650, 160, 610, 260,
           {"Category": [proy_columna(D8, "aircraft_model")],
            "Y": [proy_agregada(D8, "valid_departures")]},
           "Salidas por modelo", z=2),
    visual("p3b3", "clusteredBarChart", 20, 440, 610, 260,
           {"Category": [proy_columna(D5b, "gate_id")],
            "Series": [proy_columna(D5b, "airline")],
            "Y": [proy_agregada(D5b, "over_threshold")]},
           "Superaciones por puerta y compania", z=3),
    visual("p3t1", "tableEx", 650, 440, 610, 260,
           {"Values": [
               proy_columna(D6, "gate_id"),
               proy_columna(D6, "destination_id"),
               proy_agregada(D6, "valid_departures"),
               proy_agregada(D6, "over_threshold"),
               proy_agregada(D6, "avg_minutes_over")]},
           "Puerta y destino: muestra y exceso", z=4),
]

# ============================ ESCRITURA ============================

def escribir_modelo():
    """Anade las tablas nuevas al modelo TMDL (sin DAX: solo columnas)."""
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

    # model.tmdl con las referencias a todas las tablas
    refs = "\n".join(f"ref table {t}" for t in TABLAS)
    (DESTINO / "AeroFlow.SemanticModel" / "definition" / "model.tmdl").write_text(
        "model Model\n"
        "\tculture: es-ES\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: es-ES\n\n"
        f"{refs}\n", encoding="utf-8")


def main():
    # limpiar paginas anteriores
    shutil.rmtree(PAGES, ignore_errors=True)
    PAGES.mkdir(parents=True)

    escribir_modelo()

    paginas = [
        pagina("a1000000000000000000000000000001", "Estado general", p1, sufijo="1"),
        pagina("a2000000000000000000000000000002", "Patrones temporales", p2, sufijo="2"),
        pagina("a3000000000000000000000000000003", "Companias y aviones", p3,
               filtro_entidad="D5_companias", sufijo="3"),
    ]

    orden = []
    for pid, meta, visuales in paginas:
        orden.append(pid)
        d = PAGES / pid
        d.mkdir(parents=True)
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
