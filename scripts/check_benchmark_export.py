from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from benchmark_export import EXPORT_COLUMNS, export_benchmark_urls
from market_search import load_market_offers


def main() -> int:
    output_path = ROOT_DIR / "output" / "benchmark_urls.csv"
    market_rows = load_market_offers(ROOT_DIR / "output" / "market_offers.csv")
    source_row = next(row for row in market_rows if row.get("offer_id") and row.get("normalized_url"))
    export_benchmark_urls([source_row], model="TIK", output_path=output_path)

    with output_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        columns = tuple(handle.seek(0) or csv.DictReader(handle).fieldnames or [])

    failures: list[str] = []
    if not output_path.exists():
        failures.append("benchmark_urls_missing")
    if columns != EXPORT_COLUMNS:
        failures.append("required_columns")
    if not rows:
        failures.append("no_exported_rows")
    for row in rows:
        if not row.get("normalized_url"):
            failures.append("empty_normalized_url")
        if not all(row.get(field) for field in ("brand", "category", "model")):
            failures.append("missing_context_fields")
        if "e+" in row.get("offer_id", "").lower():
            failures.append("scientific_offer_id")
        if "raw_url" in row or "nearby_text" in row:
            failures.append("technical_columns_exported")

    if failures:
        print("FAIL")
        for failure in sorted(set(failures)):
            print(failure)
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
