from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DRAFT_PATH = ROOT_DIR / "output" / "benchmark_draft.csv"
SOURCES_PATH = ROOT_DIR / "output" / "benchmark_sources.csv"
DRAFT_FIELDS = ("brand", "category", "detected_model", "offer_id", "normalized_url", "Rama", "Koła", "Udźwig", "Regulacja oparcia", "Auto-folding", "Składanie jedną ręką", "Waga", "Wymiary po złożeniu", "Siedzisko", "Amortyzacja", "Koła 360°", "Hamulec", "Budka XXL", "Filtr UPF50+", "Wodoodporna budka", "Regulacja rączki", "Wymiary oparcia / miejsce do spania", "Akcesoria", "confidence_summary", "value_type_summary", "data_status_summary", "negative_fields", "missing_fields", "source_evidence_count")
SOURCE_FIELDS = ("offer_id", "detected_model", "normalized_url", "field_name", "evidence", "evidence_source", "confidence", "value_type")


def main() -> int:
    result = subprocess.run([sys.executable, str(ROOT_DIR / "scripts" / "build_benchmark_draft.py")], cwd=ROOT_DIR, capture_output=True, text=True, check=False)
    failures: list[str] = []
    if result.returncode != 0:
        failures.append("build_script_failed")
    draft_rows: list[dict[str, str]] = []
    source_rows: list[dict[str, str]] = []
    if not DRAFT_PATH.exists() or not SOURCES_PATH.exists():
        failures.append("outputs_missing")
    if DRAFT_PATH.exists():
        with DRAFT_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            draft_rows = list(reader)
            if tuple(reader.fieldnames or []) != DRAFT_FIELDS:
                failures.append("draft_columns")
    if SOURCES_PATH.exists():
        with SOURCES_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            source_rows = list(reader)
            if tuple(reader.fieldnames or []) != SOURCE_FIELDS:
                failures.append("source_columns")
    with (ROOT_DIR / "output" / "firecrawl_offer_queue.csv").open(encoding="utf-8", newline="") as handle:
        fetched_count = sum(row.get("status") == "fetched" for row in csv.DictReader(handle))
    if fetched_count and not draft_rows:
        failures.append("draft_empty_for_fetched")
    if any("raw_url" in row for row in draft_rows + source_rows):
        failures.append("raw_url_column")
    if any(not row.get("missing_fields") for row in draft_rows):
        failures.append("missing_fields_empty")
    for row in draft_rows:
        x_fields = {field for field in DRAFT_FIELDS[5:23] if row.get(field) == "X"}
        listed_missing = set(filter(None, row.get("missing_fields", "").split(" | ")))
        if x_fields != listed_missing:
            failures.append("missing_fields_not_aligned_with_X")
    if any(not row.get("source_evidence_count", "").isdigit() for row in draft_rows):
        failures.append("source_evidence_count_not_numeric")
    if failures:
        print("FAIL")
        for failure in failures:
            print(failure)
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
