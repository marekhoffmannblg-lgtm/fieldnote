from __future__ import annotations

import csv
import json
import argparse
from pathlib import Path

from p0_runtime import atomic_write_csv, atomic_write_json
from quality_gate import coverage_points

ROOT = Path(__file__).resolve().parent.parent
GROUPS = ROOT / "output" / "model_groups"
OUT = ROOT / "output"
CRITICAL_FIELDS = ("Waga", "Udźwig", "Regulacja oparcia", "Hamulec", "Amortyzacja", "Regulacja rączki")


def read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group-key", action="append", default=[], help="Przebuduj i scal wyłącznie wskazaną grupę.")
    args = parser.parse_args()
    scoped_keys = {str(key) for key in args.group_key if str(key).strip()}
    rows = []
    candidates = {}
    for directory in sorted(GROUPS.glob("*/model_state.json")):
        state = read(directory)
        key = state.get("group_key", "")
        if not key: continue
        candidates.setdefault(key, []).append(directory)
    for key, dirs in candidates.items():
        if scoped_keys and key not in scoped_keys:
            continue
        def canonical(path):
            state = read(path); brand = str(state.get("brand", "")).lower().replace(" ", "-"); model = str(state.get("model", "")).lower().replace(" ", "-")
            return path.parent.name == f"{brand}__{model}"
        directory = next((path for path in dirs if canonical(path)), dirs[0])
        duplicate_warning = [f"duplicate_group_key:{key}:{len(dirs)}"] if len(dirs) > 1 else []
        state = read(directory)
        group = read(directory.parent / "group.json")
        fields = state.get("fields", {})
        sources = group.get("sources", group.get("offers", []))
        marketplaces = sorted({item.get("marketplace", "allegro") for item in sources})
        valid = sum(1 for item in fields.values() if isinstance(item, dict) and coverage_points(item) == 1.0)
        weak = sum(1 for item in fields.values() if isinstance(item, dict) and coverage_points(item) == 0.5)
        confirmed = valid
        open_fields = sum(1 for item in fields.values() if not item.get("locked"))
        x_fields = sum(1 for item in fields.values() if item.get("value", "X") == "X")
        total = len(fields) or 1
        # Weak evidence contributes half a field. It is visible in the report
        # but never presented as full deterministic confirmation.
        coverage = round((valid + weak * 0.5) / total * 100, 2)
        reasons = []
        if len(sources) < 3: reasons.append(f"tylko {len(sources)} źródła")
        allegro_count = sum(item.get("marketplace", "allegro") == "allegro" for item in sources)
        if allegro_count < 3: reasons.append(f"tylko {allegro_count} źródła Allegro")
        if open_fields > 5: reasons.append(f"{open_fields} otwartych pól")
        if x_fields > 5: reasons.append(f"{x_fields} pól X")
        if coverage < 70: reasons.append(f"coverage {coverage}% poniżej 70%")
        quality_scores = [float(item.get("quality_score", 0) or 0) for item in sources]
        if len(marketplaces) == 1 and quality_scores and sum(quality_scores) / len(quality_scores) < 50: reasons.append("jeden marketplace i niska jakość źródeł")
        conflicts = [field for field, item in fields.items() if item.get("validation_status") == "conflicting" or item.get("status") == "conflicting" or (coverage_points(item) == 0.5)]
        if conflicts: reasons.append("konflikty lub evidence o niskiej pewności")
        missing_critical = [field for field in CRITICAL_FIELDS if fields.get(field, {}).get("value", "X") == "X" or fields.get(field, {}).get("status") in {"open", "unclear", "conflicting"}]
        if missing_critical: reasons.append("brak lub niepewność kluczowych pól")
        recommended = bool(reasons)
        if len(sources) < 2 or coverage < 50 or len(missing_critical) >= 3: priority = "high"
        elif recommended: priority = "medium"
        else: priority = "low"
        rows.append({"group_key": state.get("group_key", ""), "brand": state.get("brand", ""), "model": state.get("model", ""), "category": group.get("category", ""), "subcategory": group.get("subcategory", ""), "benchmark_category": group.get("benchmark_category", ""), "taxonomy_version": group.get("taxonomy_version", ""), "taxonomy_status": group.get("taxonomy_status", "review_required"), "marketplaces": ",".join(marketplaces), "sources_total": len(sources), "sources_allegro": allegro_count, "fields_confirmed": confirmed, "fields_weak": weak, "fields_open": open_fields, "fields_x": x_fields, "coverage_percent": coverage, "targeted_search_recommended": recommended, "additional_research_recommended": recommended, "research_priority": priority, "recommended_marketplaces": json.dumps(["allegro"] if allegro_count < 3 else [], ensure_ascii=False), "recommended_query": f"{state.get('brand','')} {state.get('model','')}".strip(), "missing_critical_fields": json.dumps(missing_critical, ensure_ascii=False), "recommendation_reasons": json.dumps(reasons, ensure_ascii=False), "warnings": json.dumps(duplicate_warning, ensure_ascii=False)})
    columns = tuple(rows[0]) if rows else ("group_key", "brand", "model", "category", "subcategory", "benchmark_category", "taxonomy_version", "taxonomy_status", "marketplaces", "sources_total", "sources_allegro", "fields_confirmed", "fields_weak", "fields_open", "fields_x", "coverage_percent", "targeted_search_recommended", "additional_research_recommended", "research_priority", "recommended_marketplaces", "recommended_query", "missing_critical_fields", "recommendation_reasons", "warnings")
    if scoped_keys:
        for key in scoped_keys:
            if key not in candidates:
                raise SystemExit(f"Nie znaleziono group_key: {key}")
        def merge(existing_path: Path, updates: list[dict[str, object]]) -> list[dict[str, object]]:
            existing: list[dict[str, object]] = []
            if existing_path.exists():
                with existing_path.open(encoding="utf-8", newline="") as handle:
                    existing = list(csv.DictReader(handle))
            changed = {str(item.get("group_key", "")) for item in updates}
            return [item for item in existing if str(item.get("group_key", "")) not in changed] + updates
        rows = merge(OUT / "model_coverage.csv", rows)
    atomic_write_csv(OUT / "model_coverage.csv", columns, rows)
    atomic_write_json(OUT / "model_coverage.json", rows)
    print(f"coverage_models={len(rows)}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
