from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from firecrawl_loader import load_firecrawl_documents
from listing_parser import parse_markdown_listings
from scoring import score_listing
from url_normalizer import normalize_allegro_url


ROOT_DIR = Path(__file__).resolve().parent.parent
PRODUCTS_CSV = ROOT_DIR / "input" / "products.csv"
FIRECRAWL_DIR = ROOT_DIR / "input" / "firecrawl_listings"
OUTPUT_CSV = ROOT_DIR / "output" / "found_urls.csv"
OUTPUT_COLUMNS = (
    "brand",
    "model",
    "category",
    "source_file",
    "page_url",
    "offer_id",
    "title",
    "price",
    "url",
    "normalized_url",
    "is_sponsored",
    "match_score",
    "match_reason",
    "status",
)


@dataclass(frozen=True)
class Product:
    brand: str
    model: str
    category: str


@dataclass(frozen=True)
class EnrichedListing:
    source_file: str
    page_url: str
    offer_id: str
    title: str
    price: str
    url: str
    normalized_url: str
    is_sponsored: bool


def load_products(products_csv: Path) -> list[Product]:
    if not products_csv.exists():
        return []

    with products_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        products: list[Product] = []
        for row in reader:
            brand = (row.get("brand") or "").strip()
            model = (row.get("model") or "").strip()
            category = (row.get("category") or "").strip()
            if brand and model and category:
                products.append(Product(brand=brand, model=model, category=category))
        return products


def parse_documents_to_listings(documents: list) -> list[EnrichedListing]:
    listings: list[EnrichedListing] = []

    for document in documents:
        parsed_listings = parse_markdown_listings(
            document.markdown,
            source_file=document.source_file,
            page_url=document.page_url,
        )
        for listing in parsed_listings:
            normalized = normalize_allegro_url(listing.url, base_url=document.page_url)
            listings.append(
                EnrichedListing(
                    source_file=listing.source_file,
                    page_url=listing.page_url,
                    offer_id=normalized.offer_id or listing.offer_id,
                    title=listing.title,
                    price=listing.price,
                    url=listing.url,
                    normalized_url=normalized.normalized_url,
                    is_sponsored=listing.is_sponsored,
                )
            )

    return listings


def parse_all_listings() -> list[EnrichedListing]:
    documents = load_firecrawl_documents(FIRECRAWL_DIR)
    listings = parse_documents_to_listings(documents)
    return deduplicate_listings(listings)


def deduplicate_listings(listings: list[EnrichedListing]) -> list[EnrichedListing]:
    seen: set[str] = set()
    deduplicated: list[EnrichedListing] = []

    for listing in listings:
        dedupe_key = f"offer_id:{listing.offer_id}" if listing.offer_id else f"url:{listing.normalized_url}"
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduplicated.append(listing)

    return deduplicated


def build_output_rows(products: list[Product], listings: list[EnrichedListing]) -> list[dict[str, str | int | bool]]:
    rows: list[dict[str, str | int | bool]] = []
    for product in products:
        for listing in listings:
            score = score_listing(
                brand=product.brand,
                model=product.model,
                category=product.category,
                title=listing.title,
            )
            rows.append(
                {
                    "brand": product.brand,
                    "model": product.model,
                    "category": product.category,
                    "source_file": listing.source_file,
                    "page_url": listing.page_url,
                    "offer_id": listing.offer_id,
                    "title": listing.title,
                    "price": listing.price,
                    "url": listing.url,
                    "normalized_url": listing.normalized_url,
                    "is_sponsored": str(listing.is_sponsored).lower(),
                    "match_score": score.score,
                    "match_reason": "; ".join(score.reasons),
                    "status": score.status,
                }
            )
    return rows


def write_output(rows: list[dict[str, str | int | bool]], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    products = load_products(PRODUCTS_CSV)
    listings = parse_all_listings()
    rows = build_output_rows(products, listings)
    write_output(rows, OUTPUT_CSV)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
