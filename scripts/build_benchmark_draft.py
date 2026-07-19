from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
AUDIT_PATH = ROOT_DIR / "output" / "offer_page_field_audit.csv"
QUEUE_PATH = ROOT_DIR / "output" / "firecrawl_offer_queue.csv"
URLS_PATH = ROOT_DIR / "output" / "firecrawl_offer_urls.csv"
DRAFT_PATH = ROOT_DIR / "output" / "benchmark_draft.csv"
SOURCES_PATH = ROOT_DIR / "output" / "benchmark_sources.csv"
BENCHMARK_FIELDS = ("Rama", "Koła", "Udźwig", "Regulacja oparcia", "Auto-folding", "Składanie jedną ręką", "Waga", "Wymiary po złożeniu", "Siedzisko", "Amortyzacja", "Koła 360°", "Hamulec", "Budka XXL", "Filtr UPF50+", "Wodoodporna budka", "Regulacja rączki", "Wymiary oparcia / miejsce do spania", "Akcesoria")
DRAFT_COLUMNS = ("brand", "category", "detected_model", "offer_id", "normalized_url", *BENCHMARK_FIELDS, "confidence_summary", "value_type_summary", "data_status_summary", "negative_fields", "missing_fields", "source_evidence_count")
SOURCE_COLUMNS = ("offer_id", "detected_model", "normalized_url", "field_name", "evidence", "evidence_source", "confidence", "value_type")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_outputs() -> tuple[int, int]:
    queue_rows = [row for row in read_csv(QUEUE_PATH) if row.get("status") == "fetched"]
    audit_by_offer: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in read_csv(AUDIT_PATH):
        if row.get("found") != "true" or not row.get("evidence"):
            continue
        offer_id = row.get("offer_id", "")
        field_name = row.get("field_name", "")
        current = audit_by_offer[offer_id].get(field_name)
        rank = {"low": 0, "medium": 1, "high": 2}
        if current is None or rank.get(row.get("confidence", ""), 0) > rank.get(current.get("confidence", ""), 0):
            audit_by_offer[offer_id][field_name] = row

    url_rows = {row.get("offer_id", ""): row for row in read_csv(URLS_PATH)}
    draft_rows: list[dict[str, str]] = []
    source_rows: list[dict[str, str]] = []
    for queue_row in queue_rows:
        offer_id = queue_row.get("offer_id", "")
        evidence_fields = audit_by_offer.get(offer_id, {})
        counts = {"high": 0, "medium": 0, "low": 0}
        missing: list[str] = []
        negative_fields: list[str] = []
        status_counts = {"confirmed_fields": 0, "unknown_context_fields": 0, "missing_fields": 0}
        draft = {
            "brand": queue_row.get("brand", "") or "Kinderkraft",
            "category": queue_row.get("category", "") or "Wózki",
            "detected_model": queue_row.get("detected_model", ""),
            "offer_id": offer_id,
            "normalized_url": queue_row.get("normalized_url", "") or url_rows.get(offer_id, {}).get("normalized_url", ""),
        }
        for field_name in BENCHMARK_FIELDS:
            evidence_row = evidence_fields.get(field_name)
            value_type = evidence_row.get("value_type", "") if evidence_row else ""
            if evidence_row:
                source_rows.append({**{column: evidence_row.get(column, "") for column in SOURCE_COLUMNS if column != "value_type"}, "value_type": value_type})
            if evidence_row and value_type in {"positive", "negative"}:
                evidence_text = evidence_row.get("evidence", "")
                draft[field_name] = f"nie / brak — {evidence_text}" if value_type == "negative" else evidence_text
                status_counts["confirmed_fields"] += 1
                confidence = evidence_row.get("confidence", "")
                if confidence in counts:
                    counts[confidence] += 1
                if value_type == "negative":
                    negative_fields.append(field_name)
            else:
                draft[field_name] = "X"
                status_counts["unknown_context_fields" if value_type == "unknown" else "missing_fields"] += 1
                missing.append(field_name)
        draft["confidence_summary"] = "; ".join(f"{level}:{counts[level]}" for level in ("high", "medium", "low"))
        draft["value_type_summary"] = "; ".join(f"{value_type}:{sum(1 for row in evidence_fields.values() if row.get('value_type') == value_type)}" for value_type in ("positive", "negative", "unknown"))
        draft["data_status_summary"] = "; ".join(f"{status}:{status_counts[status]}" for status in ("confirmed_fields", "unknown_context_fields", "missing_fields"))
        draft["negative_fields"] = " | ".join(negative_fields)
        draft["missing_fields"] = " | ".join(missing)
        draft["source_evidence_count"] = str(sum(counts.values()))
        draft_rows.append(draft)

    DRAFT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DRAFT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DRAFT_COLUMNS)
        writer.writeheader()
        writer.writerows(draft_rows)
    with SOURCES_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_COLUMNS)
        writer.writeheader()
        writer.writerows(source_rows)
    return len(draft_rows), len(source_rows)


if __name__ == "__main__":
    draft_count, source_count = build_outputs()
    print(f"benchmark_rows={draft_count} source_rows={source_count}")
