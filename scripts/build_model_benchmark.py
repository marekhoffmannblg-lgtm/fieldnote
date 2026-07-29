from __future__ import annotations

import csv
import json
import argparse
from pathlib import Path

from benchmark_taxonomy import is_benchmark_eligible
from p0_runtime import atomic_write_csv, atomic_write_json
from quality_gate import coverage_points

ROOT = Path(__file__).resolve().parent.parent
GROUPS = ROOT / "output" / "model_groups"
OUT = ROOT / "output"
FIELDS = ("Marka", "Model", "Status", "Rama", "Koła", "Udźwig", "Regulacja oparcia", "Auto-folding", "Składanie jedną ręką", "Waga", "Wymiary po złożeniu", "Siedzisko", "Amortyzacja", "Koła 360°", "Hamulec", "Budka XXL", "Filtr UPF50+", "Wodoodporna budka", "Regulacja rączki", "Wymiary oparcia / miejsce do spania", "Akcesoria")
EVIDENCE_KEYS = ("source_id", "marketplace", "external_offer_id", "source_url", "value", "evidence")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def normalize_evidence_items(value, current_value: str = "") -> list[dict[str, str]]:
    if value is None or value == "":
        return []
    values = value if isinstance(value, list) else [value]
    normalized = []
    for item in values:
        if item is None or item == "":
            continue
        if isinstance(item, dict):
            normalized.append({key: str(item.get(key, "") or "") for key in EVIDENCE_KEYS})
        elif isinstance(item, str):
            normalized.append({"source_id": "", "marketplace": "", "external_offer_id": "", "source_url": "", "value": current_value, "evidence": item})
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group-key", action="append", default=[], help="Przebuduj i scal wyłącznie wskazaną grupę.")
    args = parser.parse_args()
    scoped_keys = {str(key) for key in args.group_key if str(key).strip()}
    columns = ("group_key", "category", "subcategory", "benchmark_category", "taxonomy_version", *FIELDS, "marketplaces_used", "sources_total", "sources_by_marketplace", "offers_used", "offers_available", "fields_confirmed", "fields_weak", "fields_x", "primary_image_url", "product_rating", "source_quality_note")
    source_columns = ("group_key", "brand", "model", "field_name", "value", "status", "confidence", "source_id", "marketplace", "external_offer_id", "source_url", "evidence")
    rows, sources = [], []
    quality = {"models_total": 0, "fields_confirmed": 0, "fields_x": 0}
    candidates = {}
    for directory in sorted(GROUPS.iterdir() if GROUPS.exists() else []):
        state = read_json(directory / "model_state.json")
        if state.get("group_key"):
            candidates.setdefault(state["group_key"], []).append(directory)
    for key, directories in candidates.items():
        if scoped_keys and key not in scoped_keys:
            continue
        directory = next((path for path in directories if path.name == f"{read_json(path / 'model_state.json').get('brand','').lower().replace(' ','-')}__{read_json(path / 'model_state.json').get('model','').lower().replace(' ','-')}"), directories[0])
        state = read_json(directory / "model_state.json")
        group = read_json(directory / "group.json")
        if not state:
            continue
        if not is_benchmark_eligible(group):
            continue
        fields = state.get("fields", {})
        values = {}
        for field in FIELDS:
            item = fields.get(field, {}) if isinstance(fields.get(field, {}), dict) else {}
            values[field] = item.get("value", "X") if coverage_points(item) > 0 else "X"
        confirmed = sum(1 for field in FIELDS if coverage_points(fields.get(field, {}) if isinstance(fields.get(field, {}), dict) else {}) == 1.0)
        weak = sum(1 for field in FIELDS if coverage_points(fields.get(field, {}) if isinstance(fields.get(field, {}), dict) else {}) == 0.5)
        sources_group = group.get("sources", group.get("offers", []))
        marketplaces = sorted({item.get("marketplace", "allegro") for item in sources_group})
        by_market = {market: sum(item.get("marketplace", "allegro") == market for item in sources_group) for market in marketplaces}
        row = {"group_key": state.get("group_key", ""), "category": group.get("category", ""), "subcategory": group.get("subcategory", ""), "benchmark_category": group.get("benchmark_category", ""), "taxonomy_version": group.get("taxonomy_version", ""), **values, "marketplaces_used": ",".join(marketplaces), "sources_total": len(sources_group), "sources_by_marketplace": json.dumps(by_market, ensure_ascii=False), "offers_used": len(state.get("processed_source_ids", state.get("processed_offer_ids", []))), "offers_available": len(sources_group), "fields_confirmed": confirmed, "fields_weak": weak, "fields_x": len(FIELDS) - confirmed - weak, "primary_image_url": "", "product_rating": "", "source_quality_note": ""}
        rows.append(row)
        quality["models_total"] += 1
        quality["fields_confirmed"] += confirmed
        quality["fields_x"] += len(FIELDS) - confirmed - weak
        for field, item in fields.items():
            if field not in FIELDS:
                continue
            if not isinstance(item, dict):
                continue
            for evidence in normalize_evidence_items(item.get("evidence"), item.get("value", "X")):
                source_id = evidence.get("source_id", evidence.get("offer_id", "")); source_url = evidence.get("source_url", "")
                sources.append({"group_key": state.get("group_key", ""), "brand": state.get("brand", ""), "model": state.get("model", ""), "field_name": field, "value": evidence.get("value", item.get("value", "X")), "status": item.get("status", "open"), "confidence": item.get("confidence", "low"), "source_id": source_id, "marketplace": evidence.get("marketplace", "allegro"), "external_offer_id": evidence.get("external_offer_id", evidence.get("offer_id", "")), "source_url": source_url, "evidence": evidence.get("evidence", "")})
    if scoped_keys:
        for key in scoped_keys:
            if key not in candidates:
                raise SystemExit(f"Nie znaleziono group_key: {key}")
        def merge_csv(filename: str, fieldnames: tuple[str, ...], updates: list[dict[str, str]]) -> list[dict[str, str]]:
            path = OUT / filename
            existing: list[dict[str, str]] = []
            if path.exists():
                with path.open(encoding="utf-8", newline="") as handle:
                    existing = list(csv.DictReader(handle))
            changed = {str(item.get("group_key", "")) for item in updates}
            merged = [item for item in existing if str(item.get("group_key", "")) not in changed]
            merged.extend(updates)
            return merged
        rows = merge_csv("model_benchmark.csv", columns, rows)
        sources = merge_csv("model_benchmark_sources.csv", source_columns, sources)
        quality = {"models_total": len(rows), "fields_confirmed": sum(int(item.get("fields_confirmed", 0) or 0) for item in rows), "fields_x": sum(int(item.get("fields_x", 0) or 0) for item in rows)}
    for filename, fieldnames, data in (("model_benchmark.csv", columns, rows), ("model_benchmark_sources.csv", source_columns, sources)):
        atomic_write_csv(OUT / filename, fieldnames, data)
    atomic_write_json(OUT / "model_benchmark_quality.json", quality)
    print(f"models={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
