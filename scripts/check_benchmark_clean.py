from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

from build_benchmark_draft import BENCHMARK_FIELDS


ROOT_DIR = Path(__file__).resolve().parent.parent
CLEAN_PATH = ROOT_DIR / "output" / "benchmark_clean.csv"
SOURCES_PATH = ROOT_DIR / "output" / "benchmark_clean_sources.csv"
CLEAN_COLUMNS = ("brand", "category", "detected_model", "offer_id", "normalized_url", *BENCHMARK_FIELDS)
SOURCE_COLUMNS = ("offer_id", "detected_model", "field_name", "clean_value", "evidence", "confidence", "normalized_url", "clean_status")
NOISE = ("https://", "![", "](", "allegroimg", "Rowerek Biegowy", "TORBA DO WÓZKA", "Fotelik samochodowy", "Lionelo")


def main() -> int:
    result = subprocess.run([sys.executable, str(ROOT_DIR / "scripts" / "build_benchmark_clean.py")], cwd=ROOT_DIR, capture_output=True, text=True, check=False)
    failures: list[str] = []
    if result.returncode != 0:
        failures.append("build_script_failed")
    if not CLEAN_PATH.exists() or not SOURCES_PATH.exists():
        failures.append("outputs_missing")
    rows: list[dict[str, str]] = []
    source_rows: list[dict[str, str]] = []
    if CLEAN_PATH.exists():
        with CLEAN_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            if tuple(reader.fieldnames or []) != CLEAN_COLUMNS:
                failures.append("clean_columns")
    if SOURCES_PATH.exists():
        with SOURCES_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            source_rows = list(reader)
            if tuple(reader.fieldnames or []) != SOURCE_COLUMNS:
                failures.append("source_columns")
    if CLEAN_PATH.exists() and not rows:
        failures.append("clean_empty")
    for row in rows:
        if not row.get("normalized_url", "").strip():
            failures.append("empty_normalized_url")
        if "raw_url" in row or "nearby_text" in row:
            failures.append("technical_column_present")
        for field_name in BENCHMARK_FIELDS:
            if len(row.get(field_name, "")) > 160:
                failures.append("clean_value_over_160_chars")
            if any(marker.lower() in row.get(field_name, "").lower() for marker in NOISE):
                failures.append("noise_in_clean_value")
            if field_name == "Udźwig" and re.fullmatch(r"\d+(?:[.,]\d+)?\s*kg", row.get(field_name, ""), re.IGNORECASE):
                failures.append("payload_only_udzwig")
    clean_by_key = {(row.get("offer_id", ""), row.get("field_name", "")): row for row in source_rows}
    for source in source_rows:
        if source.get("clean_status") not in {"extracted", "x_missing", "rejected_noise"}:
            failures.append("invalid_clean_status")
        if len(source.get("clean_value", "")) > 160:
            failures.append("source_clean_value_over_160_chars")
        if source.get("clean_status") in {"x_missing", "rejected_noise"} and source.get("clean_value") != "X":
            failures.append("unsafe_value_not_X")
    if failures:
        print("FAIL")
        for failure in sorted(set(failures)):
            print(failure)
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
