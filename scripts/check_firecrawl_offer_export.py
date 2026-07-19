from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from firecrawl_offer_export import FIRECRAWL_EXPORT_COLUMNS, export_firecrawl_offer_urls
from market_search import enrich_market_rows, load_market_offers
from prepare_firecrawl_offer_queue import QUEUE_COLUMNS, prepare_queue


def main() -> int:
    export_path = ROOT_DIR / "output" / "firecrawl_offer_urls.csv"
    market_rows = enrich_market_rows(load_market_offers(ROOT_DIR / "output" / "market_offers.csv"))
    export_firecrawl_offer_urls(market_rows, output_path=export_path, export_reason="test_all_auctions")

    with export_path.open(encoding="utf-8", newline="") as handle:
        export_reader = csv.DictReader(handle)
        export_rows = list(export_reader)
        export_columns = tuple(export_reader.fieldnames or [])
    with tempfile.TemporaryDirectory() as temporary_dir:
        queue_path = Path(temporary_dir) / "firecrawl_offer_queue.csv"
        prepare_queue(export_path, queue_path)
        with queue_path.open(encoding="utf-8", newline="") as handle:
            queue_reader = csv.DictReader(handle)
            queue_rows = list(queue_reader)
            queue_columns = tuple(queue_reader.fieldnames or [])

    failures: list[str] = []
    if export_columns != FIRECRAWL_EXPORT_COLUMNS:
        failures.append("required_export_columns")
    if "raw_url" in export_columns:
        failures.append("raw_url_exported")
    if not export_rows:
        failures.append("no_export_rows")
    for row in export_rows:
        url = row.get("normalized_url", "")
        if not url:
            failures.append("empty_normalized_url")
        if "allegrolokalnie.pl" in url:
            failures.append("allegrolokalnie_exported")
        if "allegro.pl" not in url:
            failures.append("non_allegro_url")
    if queue_columns != QUEUE_COLUMNS:
        failures.append("required_queue_columns")
    if not queue_rows:
        failures.append("no_queue_rows")
    for row in queue_rows:
        if row.get("status") != "pending":
            failures.append("queue_not_pending")
        if not row.get("output_dir"):
            failures.append("queue_output_dir_missing")

    if failures:
        print("FAIL")
        for failure in sorted(set(failures)):
            print(failure)
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
