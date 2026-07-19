from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "output" / "firecrawl_offer_queue.csv"
PAGES = ROOT / "input" / "firecrawl_offer_pages"
OUT = ROOT / "output"
FIELDS = ("Marka", "Model", "Status", "Rama", "Koła", "Udźwig", "Regulacja oparcia", "Auto-folding", "Składanie jedną ręką", "Waga", "Wymiary po złożeniu", "Siedzisko", "Amortyzacja", "Koła 360°", "Hamulec", "Budka XXL", "Filtr UPF50+", "Wodoodporna budka", "Regulacja rączki", "Wymiary oparcia / miejsce do spania", "Akcesoria")
NOISE = ("dbamy o twoją prywatność", "podobne oferty", "sponsorowane", "przewidywana dostawa", "dodaj do koszyka", "kup i zapłać", "https://a.allegroimg.com", "events/clicks", "![")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def normalize_images(value: object, warnings: list[str]) -> list[dict[str, str | bool]]:
    if not isinstance(value, list):
        if value not in (None, "", {}): warnings.append("product_images has unexpected format")
        return []
    normalized = []
    for item in value:
        if isinstance(item, str):
            normalized.append({"image_url": item, "alt_text": "", "is_primary_candidate": False})
        elif isinstance(item, dict):
            url = item.get("image_url", "")
            if isinstance(url, str):
                normalized.append({"image_url": url, "alt_text": str(item.get("alt_text", "")), "is_primary_candidate": bool(item.get("is_primary_candidate", False))})
            else:
                warnings.append("product_images object without string image_url")
        else:
            warnings.append("product_images contains unsupported item")
    return normalized


def main() -> int:
    with QUEUE.open(encoding="utf-8", newline="") as handle:
        fetched = [row for row in csv.DictReader(handle) if row.get("status", "").lower() == "fetched"]
    benchmark_cols = ("offer_id", "source_url", "detected_title", "price", *FIELDS, "primary_image_url", "product_rating", "product_reviews_count", "source_quality_note")
    source_cols = ("offer_id", "field_name", "value", "status", "confidence", "evidence", "source_url")
    rows, sources, report = [], [], {"offers_total": 0, "fields_confirmed": 0, "fields_rejected": 0, "fields_not_found": 0, "warnings": []}
    for queue_row in fetched:
        offer_id = queue_row.get("offer_id", ""); directory = PAGES / offer_id; facts = read_json(directory / "product_facts_ai.json")
        if not facts: continue
        source_url = str(facts.get("source_url", queue_row.get("normalized_url", "")))
        row = {key: "" for key in benchmark_cols}; row.update({"offer_id": offer_id, "source_url": source_url, "detected_title": facts.get("detected_title", ""), "price": facts.get("price", "")})
        image_warnings: list[str] = []
        images = normalize_images(facts.get("product_images", []), image_warnings)
        if image_warnings: report["warnings"].extend(f"{offer_id}: {warning}" for warning in image_warnings)
        primary = next((image.get("image_url", "") for image in images if image.get("is_primary_candidate")), "") or next((image.get("image_url", "") for image in images), "")
        row["primary_image_url"] = primary
        reviews = facts.get("reviews_summary", {}); row["product_rating"] = reviews.get("rating", ""); row["product_reviews_count"] = reviews.get("reviews_count", "")
        quality = facts.get("source_quality", {}); row["source_quality_note"] = "; ".join(quality.get("notes", []))
        for field in FIELDS:
            item = facts.get("fields", {}).get(field, {})
            if not isinstance(item, dict): item = {}
            value = str(item.get("value", "X") or "X"); evidence = str(item.get("evidence", "") or "")[:300]; status = str(item.get("status", "not_found")); confidence = str(item.get("confidence", "low"))
            if field == "Marka" and value == "X" and facts.get("detected_brand"):
                value, status, confidence, evidence = str(facts["detected_brand"]), "confirmed", "high", f"detected_brand z offer_sections.json: {facts['detected_brand']}"
            if field == "Model" and value == "X" and facts.get("detected_model"):
                value, status, confidence, evidence = str(facts["detected_model"]), "confirmed", "high", f"detected_model z offer_sections.json: {facts['detected_model']}"
            if value != "X" and (not evidence or any(marker in (value + " " + evidence).lower() for marker in NOISE)):
                value, status = "X", "unclear"; report["fields_rejected"] += 1
            elif value == "X": report["fields_not_found"] += 1
            else: report["fields_confirmed"] += 1
            row[field] = value
            sources.append({"offer_id": offer_id, "field_name": field, "value": value, "status": status, "confidence": confidence, "evidence": evidence, "source_url": source_url})
        rows.append(row); report["offers_total"] += 1
    OUT.mkdir(exist_ok=True)
    with (OUT / "benchmark_ai_validated.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=benchmark_cols); writer.writeheader(); writer.writerows(rows)
    with (OUT / "benchmark_ai_sources.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=source_cols); writer.writeheader(); writer.writerows(sources)
    (OUT / "benchmark_ai_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"validated_rows={len(rows)}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
