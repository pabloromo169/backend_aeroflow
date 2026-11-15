#!/usr/bin/env python3
"""Genera un PBIP de AeroFlow con una tarjeta D9, corrigiendo los 3 errores
que detectó 'powerbi-report-author validate'."""

import json
import pathlib
import shutil
import uuid

BASE = pathlib.Path("/tmp/opencode/aeroflow_final")
if BASE.exists():
    shutil.rmtree(BASE)
BASE.mkdir(parents=True)

REPORT = BASE / "AeroFlow.Report"
MODEL = BASE / "AeroFlow.SemanticModel"
PAGE_ID = "e836f588d199437f8de2"
VISUAL_ID = "aaaa0000000000000000000000000001"
ENTIDAD = "D9_aviones_con_superacion"

(REPORT / "definition" / "pages" / PAGE_ID / "visuals" / VISUAL_ID).mkdir(parents=True)
(MODEL / "definition" / "tables").mkdir(parents=True)


def w(path, data):
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(data, encoding="utf-8")


def platform(tipo, nombre):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.1.0/schema.json",
        "metadata": {"type": tipo, "displayName": nombre},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }


# ---------- raíz .pbip (ERROR 1 corregido: $schema de pbipProperties) ----------
w(BASE / "AeroFlow.pbip", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
    "version": "1.0",
    "artifacts": [{"report": {"path": "AeroFlow.Report"}}],
    "settings": {"enableAutoRecovery": True},
})

# ---------- informe ----------
w(REPORT / ".platform", platform("Report", "AeroFlow"))

# ERROR 2 corregido: definition.pbir necesita $schema y version 4.0
w(REPORT / "definition.pbir", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {"byPath": {"path": "../AeroFlow.SemanticModel"}},
})

w(REPORT / "definition" / "version.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
    "version": "2.0.0",
})

w(REPORT / "definition" / "report.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
    "themeCollection": {"baseTheme": {
        "name": "Fluent2-CY26SU10",
        "reportVersionAtImport": {"visual": "2.11.0", "report": "3.4.0", "page": "2.3.1"},
        "type": "SharedResources"}},
    "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
        "items": [{"name": "Fluent2-CY26SU10",
                   "path": "BaseThemes/Fluent2-CY26SU10.json",
                   "type": "BaseTheme"}]}],
    "settings": {"useStylableVisualContainerHeader": True,
                 "exportDataMode": "AllowSummarized",
                 "defaultDrillFilterOtherVisuals": True,
                 "allowChangeFilterTypes": True,
                 "useEnhancedTooltips": True,
                 "useDefaultAggregateDisplayName": True},
})

w(REPORT / "definition" / "pages" / "pages.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
    "pageOrder": [PAGE_ID],
    "activePageName": PAGE_ID,
})

w(REPORT / "definition" / "pages" / PAGE_ID / "page.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
    "name": PAGE_ID,
    "displayName": "Prueba D9",
    "displayOption": "FitToPage",
    "height": 720,
    "width": 1280,
})

# ERROR 3 corregido: el rol Values de 'card' solo admite Measure
MEDIDA = "D9 aviones con superacion"
w(REPORT / "definition" / "pages" / PAGE_ID / "visuals" / VISUAL_ID / "visual.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.5.0/schema.json",
    "name": VISUAL_ID,
    "position": {"x": 100, "y": 100, "z": 0, "width": 420, "height": 260, "tabOrder": 0},
    "visual": {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [{
            "field": {"Measure": {
                "Expression": {"SourceRef": {"Entity": ENTIDAD}},
                "Property": MEDIDA}},
            "queryRef": f"{ENTIDAD}.{MEDIDA}",
            "nativeQueryRef": "D9",
        }]}}},
        "drillFilterOtherVisuals": True,
    },
})

shutil.copytree(
    "/tmp/opencode/scaffold_out/AeroFlow.Report/StaticResources",
    REPORT / "StaticResources",
)

# ---------- modelo semántico ----------
w(MODEL / ".platform", platform("SemanticModel", "AeroFlow"))
w(MODEL / "definition.pbism", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
    "version": "1.0",
    "settings": {},
})
w(MODEL / "definition" / "database.tmdl",
  "database AeroFlow\n\tcompatibilityLevel: 1600\n")

w(MODEL / "definition" / "model.tmdl", "\n".join([
    "model Model",
    "\tculture: es-ES",
    "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
    "\tsourceQueryCulture: es-ES",
    "\tdataAccessOptions",
    "\t\tlegacyRedirects",
    "\t\treturnErrorValuesAsNull",
    "",
    f'annotation PBI_QueryOrder = ["{ENTIDAD}"]',
    "",
]))

m_expr = "\n".join([
    "let",
    '    Origen = Dremio.DatabasesV370("192.168.0.26:32010", "Disabled"),',
    '    Aeroflow = Origen{[Name="Aeroflow",Kind="Schema"]}[Data],',
    f'    Vista = Aeroflow{{[Name="{ENTIDAD}",Kind="Table"]}}[Data]',
    "in",
    "    Vista",
])

medida_dax = (
    f"CALCULATE(SUM({ENTIDAD}[valid_departures]), "
    f"{ENTIDAD}[simulation_id] = \"SIM-01\")"
)

tmdl = "\n".join([
    f"table {ENTIDAD}",
    f"\tlineageTag: {uuid.uuid4()}",
    "",
    f"\tmeasure '{MEDIDA}' = {medida_dax}",
    "\t\tformatString: 0",
    f"\t\tlineageTag: {uuid.uuid4()}",
    "",
    "\tcolumn simulation_id",
    "\t\tdataType: string",
    "\t\tisNameInferred",
    f"\t\tsourceColumn: [simulation_id]",
    f"\t\tlineageTag: {uuid.uuid4()}",
    "\t\tsummarizeBy: none",
    "\t\tisHidden",
    "",
    "\tcolumn valid_departures",
    "\t\tdataType: int64",
    "\t\tformatString: 0",
    "\t\tisNameInferred",
    f"\t\tsourceColumn: [valid_departures]",
    f"\t\tlineageTag: {uuid.uuid4()}",
    "\t\tsummarizeBy: sum",
    "",
    "\tcolumn over_threshold_departures",
    "\t\tdataType: int64",
    "\t\tformatString: 0",
    "\t\tisNameInferred",
    f"\t\tsourceColumn: [over_threshold_departures]",
    f"\t\tlineageTag: {uuid.uuid4()}",
    "\t\tsummarizeBy: sum",
    "",
    "\tcolumn pct_departures_over_threshold",
    "\t\tdataType: double",
    "\t\tisNameInferred",
    f"\t\tsourceColumn: [pct_departures_over_threshold]",
    f"\t\tlineageTag: {uuid.uuid4()}",
    "\t\tsummarizeBy: none",
    "",
    "\tsource",
    "\t\ttype: m",
    "\t\texpression = " + m_expr.replace("\n", "\n\t\t\t"),
    "",
    "\tmode: directQuery",
    "",
])
w(MODEL / "definition" / "tables" / f"{ENTIDAD}.tmdl", tmdl)

print("generado en", BASE)
for p in sorted(BASE.rglob("*")):
    if p.is_file():
        print("  ", p.relative_to(BASE))
