from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from build_benchmark_draft import BENCHMARK_FIELDS

ROOT_DIR = Path(__file__).resolve().parent.parent
DRAFT_PATH = ROOT_DIR / "output" / "benchmark_draft.csv"
SOURCES_PATH = ROOT_DIR / "output" / "benchmark_sources.csv"
AUDIT_PATH = ROOT_DIR / "output" / "benchmark_quality_audit.csv"
SUMMARY_PATH = ROOT_DIR / "output" / "benchmark_quality_summary.json"
AUDIT_COLUMNS = ("field_name", "records_total", "records_with_value", "coverage_pct", "positive_count", "negative_count", "unknown_count", "high_count", "medium_count", "low_count", "missing_count")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run_audit() -> dict[str, object]:
    draft_rows = read_csv(DRAFT_PATH)
    source_rows = read_csv(SOURCES_PATH)
    records_total = len(draft_rows)
    source_by_key = {(row.get("offer_id", ""), row.get("field_name", "")): row for row in source_rows if row.get("evidence")}
    source_by_field: dict[str, list[dict[str, str]]] = defaultdict(list)
    for source_row in source_rows:
        if source_row.get("evidence", "").strip():
            source_by_field[source_row.get("field_name", "")].append(source_row)
    audit_rows: list[dict[str, object]] = []
    coverage: dict[str, float] = {}
    source_evidence_issues = 0
    missing_by_model: dict[str, Counter[str]] = defaultdict(Counter)
    for row in draft_rows:
        model = row.get("detected_model", "") or "Unknown"
        missing_by_model[model].update(field for field in row.get("missing_fields", "").split(" | ") if field)

    for field_name in BENCHMARK_FIELDS:
        field_sources = source_by_field[field_name]
        explicit_types = Counter(source.get("value_type", "unknown") or "unknown" for source in field_sources)
        records_with_value = sum(
            bool(row.get(field_name, "").strip()) and row.get(field_name, "").strip() != "X"
            for row in draft_rows
        )
        confidence_counts = Counter()
        value_type_counts = explicit_types
        for source in field_sources:
            confidence_counts[source.get("confidence", "low")] += 1
        for row in draft_rows:
            draft_value = row.get(field_name, "").strip()
            if not draft_value or draft_value == "X":
                continue
            source = source_by_key.get((row.get("offer_id", ""), field_name))
            if source is None or not source.get("evidence", "").strip():
                source_evidence_issues += 1
            else:
                pass
        missing_count = records_total - records_with_value
        coverage_pct = round(records_with_value / records_total * 100, 2) if records_total else 0.0
        coverage[field_name] = coverage_pct
        audit_rows.append({"field_name": field_name, "records_total": records_total, "records_with_value": records_with_value, "coverage_pct": coverage_pct, "positive_count": value_type_counts.get("positive", 0), "negative_count": value_type_counts.get("negative", 0), "unknown_count": value_type_counts.get("unknown", 0), "high_count": confidence_counts.get("high", 0), "medium_count": confidence_counts.get("medium", 0), "low_count": confidence_counts.get("low", 0), "missing_count": missing_count})

    offer_ids = [row.get("offer_id", "") for row in draft_rows if row.get("offer_id", "")]
    id_counts = Counter(offer_ids)
    positive_count = sum(int(row.get("positive_count", 0)) for row in audit_rows)
    negative_count = sum(int(row.get("negative_count", 0)) for row in audit_rows)
    unknown_count = sum(int(row.get("unknown_count", 0)) for row in audit_rows)
    summary = {
        "records_total": records_total,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "unknown_count": unknown_count,
        "confirmed_values_count": positive_count,
        "explicit_negative_count": negative_count,
        "missing_values_count": sum(int(row["missing_count"]) for row in audit_rows),
        "unknown_context_count": unknown_count,
        "duplicate_offer_ids_count": sum(count - 1 for count in id_counts.values() if count > 1),
        "empty_url_count": sum(not row.get("normalized_url", "").strip() for row in draft_rows),
        "top_coverage_fields": [field for field, _ in sorted(coverage.items(), key=lambda item: (-item[1], item[0]))[:5]],
        "low_coverage_fields": [field for field, _ in sorted(coverage.items(), key=lambda item: (item[1], item[0]))[:5]],
        "models_count": len({row.get("detected_model", "") for row in draft_rows if row.get("detected_model", "")}),
        "missing_fields_by_model": {model: dict(sorted(counter.items())) for model, counter in sorted(missing_by_model.items())},
        "source_evidence_issues_count": source_evidence_issues,
    }
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_COLUMNS)
        writer.writeheader()
        writer.writerows(audit_rows)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    summary = run_audit()
    print(f"records={summary['records_total']} source_evidence_issues={summary['source_evidence_issues_count']}")
