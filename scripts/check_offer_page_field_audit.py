from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
AUDIT_SCRIPT = ROOT_DIR / "scripts" / "audit_offer_page_fields.py"
AUDIT_CSV = ROOT_DIR / "output" / "offer_page_field_audit.csv"
SUMMARY_JSON = ROOT_DIR / "output" / "offer_page_field_audit_summary.json"
REQUIRED_COLUMNS = ("offer_id", "detected_model", "normalized_url", "field_name", "found", "value_type", "evidence", "evidence_source", "confidence")


def main() -> int:
    failures: list[str] = []
    if not AUDIT_SCRIPT.exists():
        failures.append("audit_script_missing")
    else:
        result = subprocess.run([sys.executable, str(AUDIT_SCRIPT)], cwd=ROOT_DIR, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            failures.append("audit_script_failed")

    if not AUDIT_CSV.exists() or not SUMMARY_JSON.exists():
        failures.append("audit_outputs_missing")
    if AUDIT_CSV.exists():
        with AUDIT_CSV.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            if tuple(reader.fieldnames or []) != REQUIRED_COLUMNS:
                failures.append("audit_csv_columns")
            if any(len(row.get("evidence", "")) > 300 for row in rows):
                failures.append("evidence_over_300_chars")
            if any(row.get("found") == "true" and row.get("value_type") not in {"positive", "negative", "unknown"} for row in rows):
                failures.append("invalid_value_type")
            if any(row.get("found") == "false" and row.get("value_type", "") for row in rows):
                failures.append("value_type_on_missing_field")
    if SUMMARY_JSON.exists():
        summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
        if "coverage_by_field" not in summary:
            failures.append("summary_coverage_by_field_missing")
        fetched_count = int(summary.get("fetched_pages_count", 0))
        if fetched_count and not AUDIT_CSV.stat().st_size:
            failures.append("audit_csv_empty_for_fetched_pages")

    if failures:
        print("FAIL")
        for failure in failures:
            print(failure)
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
