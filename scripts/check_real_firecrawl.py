from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from firecrawl_loader import load_firecrawl_documents
from main import FIRECRAWL_DIR, build_output_rows, deduplicate_listings, load_products, parse_documents_to_listings


TARGET_FILE = "playground-result-1783603745201.json"


def main() -> int:
    documents = [
        document
        for document in load_firecrawl_documents(FIRECRAWL_DIR)
        if document.source_file == TARGET_FILE
    ]
    if not documents:
        print(f"FAIL: file not found in input/firecrawl_listings/: {TARGET_FILE}")
        return 1

    products = load_products(ROOT_DIR / "input" / "products.csv")
    raw_listings = parse_documents_to_listings(documents)
    deduplicated = deduplicate_listings(raw_listings)
    rows = build_output_rows(products, deduplicated)
    status_counts = Counter(row["status"] for row in rows)

    print(f"Source file: {TARGET_FILE}")
    print(f"Records before deduplication: {len(raw_listings)}")
    print(f"Records after deduplication: {len(deduplicated)}")
    print(f"Records with offer_id: {sum(1 for item in deduplicated if item.offer_id)}")
    print(f"Records with normalized_url: {sum(1 for item in deduplicated if item.normalized_url)}")
    print(f"accepted: {status_counts.get('accepted', 0)}")
    print(f"review: {status_counts.get('review', 0)}")
    print(f"rejected: {status_counts.get('rejected', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
