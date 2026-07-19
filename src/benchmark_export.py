from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


EXPORT_COLUMNS = (
    "brand",
    "category",
    "model",
    "title",
    "price",
    "rating",
    "reviews_count",
    "is_sponsored",
    "normalized_url",
    "offer_id",
    "selected_at",
)


def is_real_offer_url(value: object) -> bool:
    parsed = urlparse(str(value or ""))
    allowed_host = parsed.netloc.lower().endswith(("allegro.pl", "allegrolokalnie.pl"))
    return bool(allowed_host and ("/oferta/" in parsed.path or "/produkt/" in parsed.path))


def _read_existing_rows(output_path: Path) -> list[dict[str, str]]:
    if not output_path.exists():
        return []
    with output_path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def export_benchmark_urls(
    selected_rows: list[dict[str, object]],
    *,
    model: str,
    output_path: Path,
    brand: str = "Kinderkraft",
    category: str = "Wózki",
) -> int:
    existing_rows = _read_existing_rows(output_path)
    existing_offer_ids = {str(row.get("offer_id", "")) for row in existing_rows if str(row.get("offer_id", ""))}
    rows_to_append: list[dict[str, str]] = []
    selected_at = datetime.now(timezone.utc).isoformat()

    for source_row in selected_rows:
        normalized_url = str(source_row.get("normalized_url", ""))
        offer_id = str(source_row.get("offer_id", ""))
        if not offer_id or offer_id in existing_offer_ids or not is_real_offer_url(normalized_url):
            continue
        rows_to_append.append(
            {
                "brand": brand,
                "category": category,
                "model": model or str(source_row.get("detected_model", "")),
                "title": str(source_row.get("title", "")),
                "price": str(source_row.get("price", "")),
                "rating": str(source_row.get("rating", "")),
                "reviews_count": str(source_row.get("reviews_count", "")),
                "is_sponsored": str(source_row.get("is_sponsored", "")),
                "normalized_url": normalized_url,
                "offer_id": offer_id,
                "selected_at": selected_at,
            }
        )
        existing_offer_ids.add(offer_id)

    if not rows_to_append:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output_path.exists()
    with output_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows_to_append)
    return len(rows_to_append)
