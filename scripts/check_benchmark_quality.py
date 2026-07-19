from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
AUDIT_SCRIPT = ROOT_DIR / "scripts" / "audit_benchmark_quality.py"
AUDIT_PATH = ROOT_DIR / "output" / "benchmark_quality_audit.csv"
SUMMARY_PATH = ROOT_DIR / "output" / "benchmark_quality_summary.json"
AUDIT_COLUMNS = ("field_name", "records_total", "records_with_value", "coverage_pct", "positive_count", "negative_count", "unknown_count", "high_count", "medium_count", "low_count", "missing_count")
SUMMARY_FIELDS = ("records_total", "positive_count", "negative_count", "unknown_count", "duplicate_offer_ids_count", "empty_url_count", "top_coverage_fields", "low_coverage_fields", "models_count", "missing_fields_by_model", "source_evidence_issues_count")


def main() -> int:
    failures: list[str] = []
    result = subprocess.run([sys.executable, str(AUDIT_SCRIPT)], cwd=ROOT_DIR, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        failures.append("audit_script_failed")
    if not AUDIT_PATH.exists() or not SUMMARY_PATH.exists():
        failures.append("audit_outputs_missing")
    if AUDIT_PATH.exists():
        with AUDIT_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            if tuple(reader.fieldnames or []) != AUDIT_COLUMNS:
                failures.append("audit_columns")
            for row in rows:
                try:
                    float(row.get("coverage_pct", ""))
                except ValueError:
                    failures.append("coverage_pct_not_numeric")
    if SUMMARY_PATH.exists():
        import json
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        for field in SUMMARY_FIELDS:
            if field not in summary:
                failures.append(f"summary_missing:{field}")
        draft_path = ROOT_DIR / "output" / "benchmark_draft.csv"
        draft_rows = list(csv.DictReader(draft_path.open(encoding="utf-8", newline=""))) if draft_path.exists() else []
        if draft_rows and int(summary.get("records_total", 0)) <= 0:
            failures.append("records_total_not_positive")
        if not isinstance(summary.get("duplicate_offer_ids_count"), int):
            failures.append("duplicate_count_not_numeric")
        for field in ("positive_count", "negative_count", "unknown_count"):
            if not isinstance(summary.get(field), int):
                failures.append(f"{field}_not_numeric")
    if failures:
        print("FAIL")
        for failure in sorted(set(failures)):
            print(failure)
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
