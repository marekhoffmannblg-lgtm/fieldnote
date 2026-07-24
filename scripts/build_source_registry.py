"""Build the source registry globally or update only offer IDs from one research run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

from catalog_registry import ensure_catalog_product
from run_context import load_offer_ids


ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "output" / "firecrawl_offer_queue.csv"
PAGES = ROOT / "input" / "firecrawl_offer_pages"
MANUFACTURER_SOURCES = ROOT / "input" / "manufacturer_sources"
OUT = ROOT / "output"
FIELDS = (
    "source_id", "marketplace", "source_type", "external_offer_id", "source_url", "canonical_url",
    "brand", "normalized_brand", "model", "normalized_model", "title", "seller_name", "seller_rating",
    "product_id", "group_key", "category", "benchmark_category", "category_key", "benchmark_group", "category_classification_status",
    "country", "language", "fetched_at", "offer_sections_path", "seller_info_path", "product_images_path",
    "product_facts_ai_path", "content_path", "manufacturer_source_path", "authority_level", "domain",
    "content_hash", "content_family_id", "quality_score", "quality_reasons", "eligible_for_grouping", "warnings",
)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def content_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_registry(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def make_record(queue_row: dict[str, str]) -> dict:
    offer_id = str(queue_row.get("offer_id", "")).strip()
    directory = PAGES / offer_id
    sections_data = read_json(directory / "offer_sections.json")
    seller = read_json(directory / "seller_info.json")
    # Queue metadata comes from the intentional targeted search. It is more
    # reliable for identity than a detected page heading, which can be polluted
    # by a previous product context (e.g. CYBEX page labelled Kinderkraft).
    target_brand = str(queue_row.get("brand") or "").strip()
    target_model = str(queue_row.get("detected_model") or "").strip()
    detected_brand = str(sections_data.get("detected_brand") or "").strip()
    detected_model = str(sections_data.get("detected_model") or "").strip()
    brand = target_brand or detected_brand
    model = target_model or detected_model
    product = ensure_catalog_product(brand, model) if brand and model else {}
    if product:
        brand = str(product["brand"])
        model = str(product["model"])
    sections = sections_data.get("sections", {})
    sections = sections if isinstance(sections, dict) else {}
    quality = sum(
        points
        for name, points in (("technical_details", 30), ("description", 25), ("parameters", 20), ("reviews", 10))
        if sections.get(name)
    )
    if seller.get("seller_name") or seller.get("seller_rating"):
        quality += 10
    eligible = bool(
        brand
        and model
        and model.lower() not in {"accessory / part", "accessory", "part"}
        and (directory / "offer_sections.json").exists()
    )
    technical_clean = directory / "technical_clean.md"
    source_url = str(sections_data.get("source_url", queue_row.get("normalized_url", "")))
    warnings = [] if eligible else ["uncertain_brand_or_model"]
    if target_brand and detected_brand and norm(target_brand) != norm(detected_brand):
        warnings.append("detected_brand_mismatch_used_queue_target")
    if target_model and detected_model and norm(target_model) != norm(detected_model):
        warnings.append("detected_model_mismatch_used_queue_target")
    return {
        "source_id": f"allegro:{offer_id}",
        "marketplace": "allegro",
        "source_type": "marketplace_offer",
        "external_offer_id": offer_id,
        "source_url": source_url,
        "canonical_url": source_url,
        "brand": brand,
        "normalized_brand": norm(brand),
        "model": model,
        "normalized_model": norm(model),
        "title": sections_data.get("detected_title", ""),
        "seller_name": seller.get("seller_name", ""),
        "seller_rating": seller.get("seller_rating", ""),
        "product_id": product.get("product_id", ""),
        "group_key": product.get("group_key", ""),
        "category": product.get("category", ""),
        "benchmark_category": product.get("benchmark_category", ""),
        "category_key": product.get("category_key", ""),
        "benchmark_group": product.get("benchmark_group", ""),
        "category_classification_status": product.get("category_classification_status", "requires_classification"),
        "country": "PL",
        "language": "pl",
        "fetched_at": queue_row.get("fetched_at", ""),
        "offer_sections_path": relative(directory / "offer_sections.json"),
        "seller_info_path": relative(directory / "seller_info.json"),
        "product_images_path": relative(directory / "product_images.json"),
        "product_facts_ai_path": relative(directory / "product_facts_ai.json") if (directory / "product_facts_ai.json").exists() else "",
        "content_path": relative(technical_clean) if technical_clean.exists() else "",
        "manufacturer_source_path": "",
        "authority_level": "secondary",
        "domain": urlparse(source_url).netloc.lower(),
        "content_hash": content_hash(technical_clean),
        "content_family_id": "",
        "quality_score": quality,
        "quality_reasons": [],
        "eligible_for_grouping": eligible,
        "warnings": warnings,
    }


def manufacturer_metadata_paths() -> list[Path]:
    if not MANUFACTURER_SOURCES.exists():
        return []
    return sorted(MANUFACTURER_SOURCES.glob("*/*/metadata.json"))


def make_manufacturer_record(metadata_path: Path) -> dict:
    metadata = read_json(metadata_path)
    directory = metadata_path.parent
    brand = str(metadata.get("brand", "")).strip()
    model = str(metadata.get("model", "")).strip()
    product = ensure_catalog_product(brand, model) if brand and model else {}
    clean_path = directory / "technical_clean.md"
    if not clean_path.exists():
        clean_path = directory / "document_text.md"
    source_url = str(metadata.get("source_url", "")).strip()
    canonical_url = str(metadata.get("canonical_url", source_url)).strip()
    model_match = metadata.get("model_match") is True
    eligible = bool(brand and model and model_match and clean_path.exists())
    warnings = metadata.get("warnings", [])
    warnings = warnings if isinstance(warnings, list) else [str(warnings)]
    return {
        "source_id": str(metadata.get("source_id", "")).strip(),
        "marketplace": "manufacturer",
        "source_type": str(metadata.get("source_type", "manufacturer_product_page")),
        "external_offer_id": "",
        "source_url": source_url,
        "canonical_url": canonical_url,
        "brand": brand,
        "normalized_brand": norm(brand),
        "model": model,
        "normalized_model": norm(model),
        "title": str(metadata.get("title", "")),
        "seller_name": "",
        "seller_rating": "",
        "product_id": product.get("product_id", ""),
        "group_key": product.get("group_key", ""),
        "category": product.get("category", ""),
        "benchmark_category": product.get("benchmark_category", ""),
        "category_key": product.get("category_key", ""),
        "benchmark_group": product.get("benchmark_group", ""),
        "category_classification_status": product.get("category_classification_status", "requires_classification"),
        "country": str(metadata.get("region", "")),
        "language": str(metadata.get("language", "")),
        "fetched_at": str(metadata.get("fetched_at", "")),
        "offer_sections_path": "",
        "seller_info_path": "",
        "product_images_path": "",
        "product_facts_ai_path": "",
        "content_path": relative(clean_path) if clean_path.exists() else "",
        "manufacturer_source_path": relative(directory),
        "authority_level": str(metadata.get("authority_level", "primary")),
        "domain": str(metadata.get("domain", urlparse(canonical_url).netloc.lower())),
        "content_hash": str(metadata.get("content_hash", "")) or content_hash(clean_path),
        "content_family_id": str(metadata.get("content_family_id", "")),
        "quality_score": 100 if eligible else 0,
        "quality_reasons": ["primary_manufacturer_source", "technical_clean_present"] if eligible else [],
        "eligible_for_grouping": eligible,
        "warnings": warnings + ([] if eligible else ["uncertain_brand_or_model"]),
    }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def write_registry(records: list[dict]) -> None:
    jsonl = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    atomic_write(OUT / "source_registry.jsonl", jsonl)
    csv_path = OUT / "source_registry.csv"
    temporary = csv_path.with_name(f".{csv_path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows([{field: record.get(field, "") for field in FIELDS} for record in records])
    temporary.replace(csv_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Buduje pełny lub przyrostowy rejestr źródeł.")
    parser.add_argument("--offer-ids-file", help="JSON/CSV/tekst z offer_id; aktualizuje tylko wskazane oferty.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        selected_ids = load_offer_ids(args.offer_ids_file) if args.offer_ids_file else set()
    except (OSError, ValueError) as exc:
        print(f"Błąd odczytu --offer-ids-file: {exc}")
        return 1

    fetched_rows: list[dict[str, str]] = []
    if QUEUE.exists():
        with QUEUE.open(encoding="utf-8", newline="") as handle:
            fetched_rows = [row for row in csv.DictReader(handle) if row.get("status", "").lower() == "fetched"]
    if args.offer_ids_file:
        fetched_rows = [row for row in fetched_rows if row.get("offer_id", "") in selected_ids]

    previous_records = read_registry(OUT / "source_registry.jsonl")
    previous_source_ids = {str(record.get("source_id", "")) for record in previous_records}
    updated_records = [make_record(row) for row in fetched_rows]
    manufacturer_records = [make_manufacturer_record(path) for path in manufacturer_metadata_paths()]
    manufacturer_records = [record for record in manufacturer_records if record.get("source_id")]
    updated_records.extend(manufacturer_records)
    if args.offer_ids_file:
        existing = previous_records
        updated_source_ids = {record["source_id"] for record in updated_records}
        records = [record for record in existing if record.get("source_id", "") not in updated_source_ids]
        records.extend(updated_records)
    else:
        records = updated_records

    deduplicated: dict[str, dict] = {}
    for record in records:
        source_id = str(record.get("source_id", "")).strip()
        if source_id:
            deduplicated[source_id] = record
    records = [deduplicated[source_id] for source_id in sorted(deduplicated)]
    write_registry(records)
    print(f"registry_records={len(records)}")
    print(f"registry_records_updated={len(updated_records)}")
    print(f"registry_records_added={sum(record['source_id'] not in previous_source_ids for record in manufacturer_records)}")
    print(f"manufacturer_registry_records={len(manufacturer_records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
