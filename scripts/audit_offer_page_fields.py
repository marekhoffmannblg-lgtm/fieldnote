from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT_DIR / "output" / "firecrawl_offer_queue.csv"
AUDIT_CSV = ROOT_DIR / "output" / "offer_page_field_audit.csv"
SUMMARY_JSON = ROOT_DIR / "output" / "offer_page_field_audit_summary.json"
CSV_COLUMNS = ("offer_id", "detected_model", "normalized_url", "field_name", "found", "value_type", "evidence", "evidence_source", "confidence")

FIELD_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    "Rama": (("rama", "medium"), ("stela", "medium")),
    "Koła": (("koła", "medium"), ("kola", "medium"), ("pu", "low"), ("eva", "low"), ("piankowe", "medium"), ("gumowe", "medium"), ("360", "low")),
    "Udźwig": (("udźwig", "high"), ("maksymalne obciążenie", "high"), ("do 22 kg", "high"), ("15 kg", "high"), ("22 kg", "high")),
    "Regulacja oparcia": (("regulacja oparcia", "high"), ("pozycja leżąca", "high"), ("oparcie", "medium")),
    "Auto-folding": (("auto folding", "high"), ("auto-folding", "high"), ("automatyczne składanie", "high")),
    "Składanie jedną ręką": (("jedną ręką", "high"), ("jedna ręka", "high"), ("składanie jedną ręką", "high")),
    "Waga": (("waga", "medium"), (" kg", "low")),
    "Wymiary po złożeniu": (("wymiary po złożeniu", "high"), ("po złożeniu", "high"), ("cm", "low")),
    "Siedzisko": (("siedzisko", "medium"), ("siedzenie", "medium")),
    "Amortyzacja": (("amortyzacja", "high"), ("amortyzowane", "high")),
    "Koła 360°": (("koła 360", "high"), ("kola 360", "high"), ("360°", "high"), ("360", "low")),
    "Hamulec": (("hamulec", "high"), ("stop & ride", "high"), ("stop ride", "high")),
    "Budka XXL": (("budka xxl", "high"), ("budka xl", "high"), ("xxl", "medium"), ("daszek", "medium"), ("budka", "medium")),
    "Filtr UPF50+": (("upf50", "high"), ("upf 50", "high"), ("upf", "medium"), ("uv", "low")),
    "Wodoodporna budka": (("wodoodporna budka", "high"), ("wodoodporny daszek", "high"), ("wodoodporny materiał", "high"), ("odporny na deszcz", "high"), ("wodoodporna", "medium"), ("osłona przeciwdeszczowa", "low")),
    "Regulacja rączki": (("regulacja rączki", "high"), ("regulowana rączka", "high"), ("rączka regulowana", "high"), ("rączka", "medium")),
    "Wymiary oparcia / miejsce do spania": (("wymiary oparcia", "high"), ("długość oparcia", "high"), ("długość leżenia", "high"), ("miejsce do spania", "high"), ("powierzchnia spania", "high"), ("pozycja leżąca", "medium"), ("oparcie", "medium")),
    "Akcesoria": (("akcesoria", "medium"), ("folia", "medium"), ("moskitiera", "medium"), ("uchwyt", "medium"), ("adapter", "medium"), ("torba", "medium"), ("kosz", "low")),
}
NEGATIVE_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    "Auto-folding": (("brak auto-foldingu", "high"), ("bez auto-foldingu", "high"), ("brak automatycznego składania", "high"), ("składanie parasolkowe", "high"), ("nie auto-folding", "high")),
    "Regulacja rączki": (("brak regulacji rączki", "high"), ("bez regulacji rączki", "high"), ("rączka stała", "high"), ("stała rączka", "high")),
}
UNKNOWN_KEYWORDS: dict[str, set[str]] = {
    "Wodoodporna budka": {"osłona przeciwdeszczowa"},
    "Wymiary oparcia / miejsce do spania": {"pozycja leżąca", "oparcie"},
}


def _plain_text(value: str) -> str:
    value = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def _evidence(text: str, keyword: str) -> str:
    lowered = text.lower()
    position = lowered.find(keyword.lower())
    if position < 0:
        return ""
    start = max(0, position - 100)
    end = min(len(text), position + len(keyword) + 180)
    fragment = " ".join(text[start:end].split())
    return fragment[:300]


def _confidence(text: str, keyword: str, base: str, evidence: str) -> str:
    context = text.lower()
    position = context.find(keyword.lower())
    nearby = context[max(0, position - 30) : position + len(keyword) + 80] if position >= 0 else ""
    if base == "high" or re.search(r"\d|:|cm|kg|upf|xxl|xl", nearby):
        return "high"
    if base == "medium":
        return "medium"
    return "low"


def audit_field(text: str, field_name: str) -> tuple[bool, str, str, str]:
    for keyword, base_confidence in NEGATIVE_RULES.get(field_name, ()):
        evidence = _evidence(text, keyword)
        if evidence:
            return True, "negative", evidence, _confidence(text, keyword, base_confidence, evidence)
    for keyword, base_confidence in FIELD_RULES[field_name]:
        evidence = _evidence(text, keyword)
        if evidence:
            value_type = "unknown" if keyword in UNKNOWN_KEYWORDS.get(field_name, set()) else "positive"
            confidence = _confidence(text, keyword, base_confidence, evidence)
            if value_type == "unknown":
                confidence = "low" if keyword == "osłona przeciwdeszczowa" else "medium"
            return True, value_type, evidence, confidence
    return False, "", "", ""


def _load_source(page_dir: Path) -> tuple[str, str]:
    markdown_path = page_dir / "markdown.md"
    if markdown_path.is_file():
        return markdown_path.read_text(encoding="utf-8", errors="replace"), "markdown"
    html_path = page_dir / "html.html"
    if html_path.is_file():
        return _plain_text(html_path.read_text(encoding="utf-8", errors="replace")), "html"
    return "", ""


def run_audit(queue_path: Path = QUEUE_PATH, audit_csv: Path = AUDIT_CSV, summary_json: Path = SUMMARY_JSON) -> dict[str, object]:
    with queue_path.open(encoding="utf-8", newline="") as handle:
        fetched_rows = [row for row in csv.DictReader(handle) if row.get("status") == "fetched"]

    audit_rows: list[dict[str, str]] = []
    available_by_field: Counter[str] = Counter()
    value_types_by_field: dict[str, Counter[str]] = {field: Counter() for field in FIELD_RULES}
    coverage_by_offer: dict[str, int] = {}
    for queue_row in fetched_rows:
        offer_id = queue_row.get("offer_id", "")
        page_dir = ROOT_DIR / queue_row.get("output_dir", "")
        source_text, source_name = _load_source(page_dir)
        found_count = 0
        for field_name in FIELD_RULES:
            found, value_type, evidence, confidence = audit_field(source_text, field_name)
            if found and value_type in {"positive", "negative"}:
                found_count += 1
                available_by_field[field_name] += 1
            if value_type:
                value_types_by_field[field_name][value_type] += 1
            audit_rows.append(
                {
                    "offer_id": offer_id,
                    "detected_model": queue_row.get("detected_model", ""),
                    "normalized_url": queue_row.get("normalized_url", ""),
                    "field_name": field_name,
                    "found": "true" if found else "false",
                    "value_type": value_type,
                    "evidence": evidence,
                    "evidence_source": source_name if found else "",
                    "confidence": confidence if found else "",
                }
            )
        coverage_by_offer[offer_id] = found_count

    total_pages = len(fetched_rows)
    coverage_by_field = {
        field_name: {
            "found_count": available_by_field[field_name],
            "positive_count": value_types_by_field[field_name]["positive"],
            "negative_count": value_types_by_field[field_name]["negative"],
            "unknown_count": value_types_by_field[field_name]["unknown"],
            "total_count": total_pages,
            "coverage": round(available_by_field[field_name] / total_pages, 4) if total_pages else 0.0,
        }
        for field_name in FIELD_RULES
    }
    missing_counts = {field: total_pages - int(data["found_count"]) for field, data in coverage_by_field.items()}
    summary = {
        "fetched_pages_count": total_pages,
        "fields_total": len(FIELD_RULES),
        "positive_count": sum(counts["positive"] for counts in value_types_by_field.values()),
        "negative_count": sum(counts["negative"] for counts in value_types_by_field.values()),
        "unknown_count": sum(counts["unknown"] for counts in value_types_by_field.values()),
        "coverage_by_field": coverage_by_field,
        "coverage_by_offer": coverage_by_offer,
        "top_missing_fields": [field for field, _ in sorted(missing_counts.items(), key=lambda item: (-item[1], item[0]))[:10]],
        "top_available_fields": [field for field, _ in sorted(available_by_field.items(), key=lambda item: (-item[1], item[0]))[:10]],
    }

    audit_csv.parent.mkdir(parents=True, exist_ok=True)
    with audit_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(audit_rows)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    if not QUEUE_PATH.exists():
        print("Brak output/firecrawl_offer_queue.csv")
        return 1
    summary = run_audit()
    print(f"audited_pages={summary['fetched_pages_count']} fields={summary['fields_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
