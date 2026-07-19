from __future__ import annotations

import csv
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT_DIR / "output" / "firecrawl_offer_queue.csv"
REQUIRED_FILES = ("markdown.md", "html.html", "links.txt", "metadata.json", "raw_response.json")


def main() -> int:
    if not QUEUE_PATH.exists():
        print("FAIL")
        print("firecrawl_offer_queue.csv not found")
        return 1

    with QUEUE_PATH.open(encoding="utf-8", newline="") as handle:
        fetched_rows = [row for row in csv.DictReader(handle) if row.get("status") == "fetched"]

    if not fetched_rows:
        print("Brak pobranych aukcji do sprawdzenia")
        return 0

    failures: list[str] = []
    for row in fetched_rows:
        identifier = row.get("offer_id") or row.get("queue_id") or "unknown"
        output_dir = ROOT_DIR / row.get("output_dir", "")
        if not output_dir.is_dir():
            failures.append(f"{identifier}: missing_output_dir:{output_dir}")
            continue

        for filename in REQUIRED_FILES:
            if not (output_dir / filename).is_file():
                failures.append(f"{identifier}: missing_file:{filename}")

        for filename in ("markdown.md", "raw_response.json"):
            file_path = output_dir / filename
            if file_path.is_file() and not file_path.read_text(encoding="utf-8").strip():
                failures.append(f"{identifier}: empty_file:{filename}")

    if failures:
        print("FAIL")
        for failure in failures:
            print(failure)
        return 1

    print(f"Result: OK ({len(fetched_rows)} fetched auctions checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
