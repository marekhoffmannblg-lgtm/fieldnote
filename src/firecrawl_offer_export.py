from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


FIRECRAWL_EXPORT_COLUMNS = (
    "brand",
    "category",
    "detected_model",
    "title",
    "price",
    "rating",
    "reviews_count",
    "is_sponsored",
    "normalized_url",
    "offer_id",
    "source_page",
    "export_reason",
    "exported_at",
)


def is_firecrawl_ready_url(value: object) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == "allegro.pl" and ("/oferta/" in parsed.path or "/produkt/" in parsed.path)


def _dedupe_key(row: dict[str, object]) -> str:
    offer_id = str(row.get("offer_id", ""))
    if offer_id:
        return f"offer_id:{offer_id}"
    return f"url:{row.get('normalized_url', '')}"


def _existing_keys(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    with output_path.open(encoding="utf-8", newline="") as handle:
        return {_dedupe_key(row) for row in csv.DictReader(handle)}


def export_firecrawl_offer_urls(
    rows: list[dict[str, object]],
    *,
    output_path: Path,
    export_reason: str,
    detected_model: str = "",
    brand: str = "Kinderkraft",
    category: str = "Wózki",
) -> int:
    existing_keys = _existing_keys(output_path)
    exported_at = datetime.now(timezone.utc).isoformat()
    rows_to_append: list[dict[str, str]] = []

    for row in rows:
        normalized_url = str(row.get("normalized_url", ""))
        if not is_firecrawl_ready_url(normalized_url):
            continue
        key = _dedupe_key(row)
        if key in existing_keys:
            continue
        rows_to_append.append(
            {
                "brand": brand,
                "category": category,
                "detected_model": detected_model or str(row.get("detected_model", "")),
                "title": str(row.get("title", "")),
                "price": str(row.get("price", "")),
                "rating": str(row.get("rating", "")),
                "reviews_count": str(row.get("reviews_count", "")),
                "is_sponsored": str(row.get("is_sponsored", "")),
                "normalized_url": normalized_url,
                "offer_id": str(row.get("offer_id", "")),
                "source_page": str(row.get("source_page", "")),
                "export_reason": export_reason,
                "exported_at": exported_at,
            }
        )
        existing_keys.add(key)

    if not rows_to_append:
        return 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output_path.exists()
    with output_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIRECRAWL_EXPORT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows_to_append)
    return len(rows_to_append)
