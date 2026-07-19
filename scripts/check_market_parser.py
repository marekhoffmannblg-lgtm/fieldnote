from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_offer_parser import MarketOfferCandidate, SAMPLES_ROOT, deduplicate_candidates, load_sample_pages, parse_markdown_candidates
from url_normalizer import normalize_allegro_url


EVENTS_URL = (
    "https://allegro.pl/events/clicks?redirect="
    "https%3A%2F%2Fallegro.pl%2Foferta%2Fkinderkraft-nebo-wozek-spacerowy-18405722631%3Fbi_s%3Dads"
)
DSS_URL = (
    "https://allegro.pl/dss-proxy/clicks?redirect="
    "aHR0cHM6Ly9hbGxlZ3JvLnBsL29mZXJ0YS9raW5kZXJrcmFmdC10ZXN0LTEyMzQ1Njc4OQ"
)
MARKDOWN_SAMPLE = """
Sponsorowane
![Kinderkraft Nebo Wózek Spacerowy](https://a.allegroimg.com/sample.jpg)
5,00(7)
## [Kinderkraft Nebo Wózek Spacerowy](https://allegro.pl/events/clicks?redirect=https%3A%2F%2Fallegro.pl%2Foferta%2Fkinderkraft-nebo-wozek-spacerowy-18405722631)
599,00zł
"""
MARKDOWN_PRICE_BEFORE_TITLE = """
Sponsorowane
![Kinderkraft Trig 3](https://a.allegroimg.com/sample.jpg)
436,80zł
## [Kinderkraft Trig 3](https://allegro.pl/events/clicks?type=OFFER&placement=productlisting%3Adesktop&redirect=https%3A%2F%2Fallegro.pl%2Foferta%2Fkinderkraft-trig-3-16566160258)
"""


def check_url_normalization() -> list[str]:
    failures: list[str] = []
    events_result = normalize_allegro_url(EVENTS_URL)
    if events_result.normalized_url != "https://allegro.pl/oferta/kinderkraft-nebo-wozek-spacerowy-18405722631":
        failures.append("events_redirect_normalization")

    dss_result = normalize_allegro_url(DSS_URL)
    if dss_result.normalized_url != "https://allegro.pl/oferta/kinderkraft-test-123456789":
        failures.append("dss_redirect_normalization")
    if dss_result.offer_id != "123456789":
        failures.append("dss_offer_id")
    return failures


def check_markdown_parsing() -> list[str]:
    from market_offer_parser import SamplePage

    sample_page = SamplePage(
        source_page="page_test",
        source_url="https://allegro.pl/kategoria/wozki-82593?string=kinderkraft",
        page_dir=ROOT_DIR,
        markdown_path=ROOT_DIR / "tmp.md",
        links_path=ROOT_DIR / "tmp.links",
        html_path=ROOT_DIR / "tmp.html",
    )
    sample_page.markdown_path.write_text(MARKDOWN_SAMPLE, encoding="utf-8")
    try:
        candidates = parse_markdown_candidates(sample_page)
    finally:
        sample_page.markdown_path.unlink(missing_ok=True)

    failures: list[str] = []
    if len(candidates) != 1:
        return ["markdown_candidate_count"]

    candidate = candidates[0]
    if candidate.title != "Kinderkraft Nebo Wózek Spacerowy":
        failures.append("markdown_title")
    if candidate.price != "599,00zł":
        failures.append("markdown_price")
    if candidate.rating != "5,00" or candidate.reviews_count != "7":
        failures.append("markdown_rating_reviews")
    if not candidate.image_alt_texts or candidate.image_alt_texts[0] != "Kinderkraft Nebo Wózek Spacerowy":
        failures.append("markdown_image_alts")
    return failures


def check_price_before_title_and_sponsored_url() -> list[str]:
    from market_offer_parser import SamplePage

    sample_page = SamplePage(
        source_page="page_test",
        source_url="https://allegro.pl/kategoria/wozki-82593",
        page_dir=ROOT_DIR,
        markdown_path=ROOT_DIR / "tmp.md",
        links_path=ROOT_DIR / "tmp.links",
        html_path=ROOT_DIR / "tmp.html",
    )
    sample_page.markdown_path.write_text(MARKDOWN_PRICE_BEFORE_TITLE, encoding="utf-8")
    try:
        candidates = parse_markdown_candidates(sample_page)
    finally:
        sample_page.markdown_path.unlink(missing_ok=True)

    if not candidates:
        return ["price_before_title_candidate"]
    candidate = candidates[-1]
    failures: list[str] = []
    if candidate.price != "436,80zł":
        failures.append("price_before_title")
    if not candidate.is_sponsored:
        failures.append("sponsored_from_url_or_section")
    return failures


def check_deduplication() -> list[str]:
    first = MarketOfferCandidate(
        source_page="page_1",
        source_url="u",
        source_file="a",
        source_format="links",
        offer_id="123",
        raw_url="https://allegro.pl/oferta/test-123",
        normalized_url="https://allegro.pl/oferta/test-123",
        url_type="offer",
        confidence=0.3,
    )
    second = MarketOfferCandidate(
        source_page="page_1",
        source_url="u",
        source_file="b",
        source_format="markdown",
        offer_id="123",
        raw_url="https://allegro.pl/oferta/test-123",
        normalized_url="https://allegro.pl/oferta/test-123",
        url_type="offer",
        title="Test title",
        price="199,00zł",
        confidence=0.8,
        extraction_method="markdown_h2",
    )
    deduped = deduplicate_candidates([first, second])
    if len(deduped) != 1 or deduped[0].title != "Test title":
        return ["deduplication_offer_id"]
    return []


def check_page_4() -> list[str]:
    pages = load_sample_pages(SAMPLES_ROOT)
    page_4 = next((page for page in pages if page.source_page == "page_4"), None)
    if page_4 is None:
        return ["page_4_missing"]

    candidates = parse_markdown_candidates(page_4)
    if not candidates:
        return ["page_4_no_candidates"]
    return []


def check_generated_market_offers() -> list[str]:
    output_path = ROOT_DIR / "output" / "market_offers.csv"
    if not output_path.exists():
        return ["market_offers_missing"]

    with output_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    failures: list[str] = []
    if len(rows) < 200:
        failures.append("market_offers_minimum_count")
    if any(not row.get("title") or not row.get("normalized_url") for row in rows):
        failures.append("market_offers_required_fields")
    if any(not row.get("offer_id", "").isdigit() or "e+" in row.get("offer_id", "").lower() for row in rows):
        failures.append("market_offers_offer_id_format")

    expected_sponsored_prices = {
        "14067359270": "253,40 zł",
        "16566160258": "436,80 zł",
    }
    by_offer_id = {row["offer_id"]: row for row in rows}
    for offer_id, expected_price in expected_sponsored_prices.items():
        row = by_offer_id.get(offer_id)
        if not row or row.get("is_sponsored") != "true" or row.get("price") != expected_price:
            failures.append(f"sponsored_price_{offer_id}")
    return failures


def main() -> int:
    failures = []
    failures.extend(check_url_normalization())
    failures.extend(check_markdown_parsing())
    failures.extend(check_price_before_title_and_sponsored_url())
    failures.extend(check_deduplication())
    failures.extend(check_page_4())
    failures.extend(check_generated_market_offers())

    if failures:
        print("FAIL")
        for item in failures:
            print(item)
        return 1

    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
