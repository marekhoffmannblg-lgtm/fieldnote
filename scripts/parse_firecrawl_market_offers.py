from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_offer_parser import SAMPLES_ROOT, deduplicate_candidates, load_sample_pages, parse_all_candidates, write_market_offers_csv


def main() -> int:
    pages = load_sample_pages(SAMPLES_ROOT)
    candidates = parse_all_candidates(pages)
    deduplicated = deduplicate_candidates(candidates)
    write_market_offers_csv(deduplicated)
    print(f"pages={len(pages)}")
    print(f"before_dedup={len(candidates)}")
    print(f"after_dedup={len(deduplicated)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
