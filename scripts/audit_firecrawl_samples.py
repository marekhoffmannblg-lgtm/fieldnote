from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_offer_parser import SAMPLES_ROOT, build_audit, load_sample_pages, write_audit_outputs


def main() -> int:
    pages = load_sample_pages(SAMPLES_ROOT)
    rows, summary = build_audit(pages)
    write_audit_outputs(rows, summary)
    print(f"pages={summary['pages_count']}")
    print(f"before_dedup={summary['offer_candidates_before_deduplication']}")
    print(f"after_dedup={summary['offer_candidates_after_deduplication']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
