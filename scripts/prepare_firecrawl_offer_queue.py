from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from firecrawl_offer_export import is_firecrawl_ready_url


INPUT_PATH = ROOT_DIR / "output" / "firecrawl_offer_urls.csv"
OUTPUT_PATH = ROOT_DIR / "output" / "firecrawl_offer_queue.csv"
QUEUE_COLUMNS = (
    "queue_id", "offer_id", "normalized_url", "brand", "category", "detected_model",
    "status", "output_dir", "fetched_at", "error_message", "retry_count",
    "last_attempt_at", "last_error_at",
)


def _queue_key(row: dict[str, str]) -> str:
    return f"offer_id:{row['offer_id']}" if row.get("offer_id") else f"url:{row.get('normalized_url', '')}"


def prepare_queue(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> int:
    if not input_path.exists():
        print("firecrawl_offer_urls.csv not found")
        return 0

    with input_path.open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))

    existing_rows: dict[str, dict[str, str]] = {}
    if output_path.exists():
        with output_path.open(encoding="utf-8", newline="") as handle:
            existing_rows = {_queue_key(row): row for row in csv.DictReader(handle)}

    queue_rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for index, row in enumerate(source_rows, start=1):
        normalized_url = row.get("normalized_url", "")
        if not is_firecrawl_ready_url(normalized_url):
            continue
        offer_id = row.get("offer_id", "")
        dedupe_key = f"offer_id:{offer_id}" if offer_id else f"url:{normalized_url}"
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        existing = existing_rows.get(dedupe_key, {})
        queue_id = existing.get("queue_id") or f"offer-{index:04d}"
        folder_name = offer_id or queue_id
        output_dir = f"input/firecrawl_offer_pages/{folder_name}/"
        (ROOT_DIR / output_dir).mkdir(parents=True, exist_ok=True)
        queue_rows.append(
            {
                "queue_id": queue_id,
                "offer_id": offer_id,
                "normalized_url": normalized_url,
                "brand": row.get("brand", ""),
                "category": row.get("category", ""),
                "detected_model": row.get("detected_model", ""),
                "status": existing.get("status", "pending"),
                "output_dir": existing.get("output_dir") or output_dir,
                "fetched_at": existing.get("fetched_at", ""),
                "error_message": existing.get("error_message", ""),
                # Preserve retry history when the queue is regenerated from exports.
                "retry_count": existing.get("retry_count") or "0",
                "last_attempt_at": existing.get("last_attempt_at", ""),
                "last_error_at": existing.get("last_error_at", ""),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_COLUMNS)
        writer.writeheader()
        writer.writerows(queue_rows)
    return len(queue_rows)


if __name__ == "__main__":
    print(f"prepared={prepare_queue()}")
