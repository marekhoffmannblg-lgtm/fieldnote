from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from listing_parser import parse_markdown_listings


MARKDOWN_SAMPLE = """
## Sponsorowane
## [Kinderkraft NUBI 2 wózek spacerowy](https://allegro.pl/oferta/kinderkraft-nubi-2-wozek-spacerowy-123456789?bi_s=ads)
899,00 zł

## [Polityka cookies](https://allegro.pl/pomoc/polityka-cookies)

## [Lionelo Annet Plus wózek spacerowy](https://allegro.pl/oferta/lionelo-annet-plus-987654321)
749,99 zł
"""


def main() -> int:
    listings = parse_markdown_listings(
        MARKDOWN_SAMPLE,
        source_file="sample.json",
        page_url="https://allegro.pl/listing?string=wozek",
    )

    if len(listings) != 2:
        print(f"FAIL: expected 2 listings, got {len(listings)}")
        return 1

    first = listings[0]
    checks = [
        (first.title == "Kinderkraft NUBI 2 wózek spacerowy", "title"),
        (first.price == "899,00 zł", "price"),
        (first.url.startswith("https://allegro.pl/oferta/"), "url"),
        (first.offer_id == "123456789", "offer_id"),
        (first.is_sponsored is True, "is_sponsored"),
    ]

    for passed, label in checks:
        if not passed:
            print(f"FAIL: parser check failed for {label}")
            return 1

    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
