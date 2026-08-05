"""Offline audit of the 21 canonical stroller attributes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark_relative_scoring import load_schema, normalize_attribute

ROOT = Path(__file__).resolve().parents[1]
SPECS_ROOT = ROOT / "data/internal_specs"


def load_products(specs_root: Path = SPECS_ROOT) -> list[dict[str, Any]]:
    products = []
    for path in sorted(specs_root.glob("lionelo__*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        products.append({"product_id": str(value.get("product_id") or path.stem), "model": value.get("model", path.stem), "attributes": value.get("attributes", [])})
    return products


def audit_attributes(products: list[dict[str, Any]] | None = None, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    products = products if products is not None else load_products(); schema = schema or load_schema()
    decisions = []
    for definition in schema["attributes"]:
        key = str(definition["key"]); present = 0
        for product in products:
            values = {str(item.get("key")): item for item in product.get("attributes", []) if isinstance(item, dict)}
            if normalize_attribute(values.get(key), target_unit=str(definition.get("unit", "")), value_type=str(definition.get("type", "text"))) is not None: present += 1
        decisions.append({"key": key, "role": definition.get("role", "informational"), "coverage": round(present / len(products), 4) if products else 0.0, "present": present, "total": len(products), "reason": "source field present in canonical internal specs" if present else "no usable value in fixture"})
    return {"schema_version": schema["schema_version"], "product_count": len(products), "field_count": len(decisions), "decisions": decisions}


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Audyt atrybutów wózków", "", f"Schema: `{report['schema_version']}`; produktów: **{report['product_count']}**; pól: **{report['field_count']}**", "", "| Pole | Decyzja | Pokrycie | Uzasadnienie |", "|---|---|---:|---|"]
    lines += [f"| `{item['key']}` | `{item['role']}` | {item['present']}/{item['total']} | {item['reason']} |" for item in report["decisions"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    report = audit_attributes(); output = ROOT / "docs/audit/STROLLER_ATTRIBUTE_AUDIT.md"; output.parent.mkdir(parents=True, exist_ok=True); output.write_text(render_markdown(report), encoding="utf-8"); print(json.dumps(report, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
