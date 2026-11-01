"""Build contracts from a reviewed extract of the public KRX specifications."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("extract", type=Path)
args = parser.parse_args()
source = json.loads(args.extract.read_text(encoding="utf-8"))
root = Path(__file__).resolve().parents[1]
datasets = {}
for dataset in source:
    item = dict(dataset)
    item["production_path"] = item["production_path"].removesuffix(".json")
    item["endpoint_verification"] = "Production endpoint and wire fields checked against this dataset's downloadable public developer specification. Authenticated live calls are not part of this release verification."
    for field in item["fields"]:
        name = field["name"]
        field["semantic_type"] = "date" if name == "BAS_DD" else "identifier" if name == "ISU_CD" else "text" if name in ["ISU_NM", "MKT_NM", "SECT_TP_NM"] else "decimal"
        if field["semantic_type"] == "decimal":
            field["missing_marker"] = field.get("default", "-")
            field["nonnegative"] = name not in ["CMPPREVDD_PRC", "FLUC_RT"]
            field["unit"] = None
            field["unit_status"] = "Not specified in the referenced field definition; confirm with the provider before unit-sensitive analysis."
    datasets[item["market"]] = item
catalog = {"contract_version": "0.1.0", "wire_definition_source": "KRX public developer specifications", "semantic_rules_owner": "krx-openapi-tools; normalization and validation rules are project decisions", "datasets": datasets}
(root / "krx_openapi_tools/contracts.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for market, item in datasets.items():
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": item["title"], "description": "Raw wire shape. Use the Python validator for calendar dates, grouping, nonnegative quantities, duplicate records, and expected-date checks.", "type": "object", "required": [item["block"]], "properties": {item["block"]: {"type": "array", "items": {"type": "object", "required": [f["name"] for f in item["fields"]], "properties": {f["name"]: {"type": "string", "description": f["label"]} for f in item["fields"]}, "additionalProperties": True}}}, "additionalProperties": True, "x-source": item["source_url"], "x-verified-on": item["verified_on"]}
    (root / "schemas" / f"{market}-daily.schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
