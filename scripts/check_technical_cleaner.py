from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "input" / "firecrawl_offer_pages"
REQUIRED = ("technical_clean.md", "offer_sections.json", "product_images.json", "seller_info.json", "technical_clean_summary.json")
FORBIDDEN = ("Dbamy o Twoją prywatność", "Podobne oferty", "Sponsorowane", "https://a.allegroimg.com", "events/clicks", "![", "## Propozycje dla Ciebie", "## Warunki oferty", "## Opcje zakupu", "## Zamów zestaw w jednej przesyłce", "### Zamów zestaw w jednej przesyłce", "Dodaj zestaw do koszyka", "dodaj do koszyka", "KUP I ZAPŁAĆ", "Przewidywana dostawa", "Co sądzisz o tej stronie?", "[Wszystkie parametry](", "[Odpowiedzialność za produkt](", "[Bezpieczeństwo, zgodność i ostrzeżenia](", "Zamknij", "cena za")


def main() -> int:
    failures = []
    script = ROOT / "scripts" / "clean_offer_pages_technical.py"
    if not script.exists():
        failures.append("script_missing")
    result = subprocess.run([sys.executable, str(script), "--limit", "3"], cwd=ROOT, capture_output=True, text=True) if script.exists() else None
    if result and result.returncode != 0:
        failures.append("cleaner_failed")
    with (ROOT / "output" / "firecrawl_offer_queue.csv").open(encoding="utf-8", newline="") as handle:
        fetched = [row for row in csv.DictReader(handle) if row.get("status") == "fetched"][:3]
    for row in fetched:
        directory = PAGES / row.get("offer_id", "")
        for name in REQUIRED:
            if not (directory / name).exists():
                failures.append(f"missing:{row.get('offer_id')}:{name}")
        clean = directory / "technical_clean.md"
        if clean.exists():
            text = clean.read_text(encoding="utf-8")
            for marker in FORBIDDEN:
                if marker.lower() in text.lower():
                    failures.append(f"noise:{row.get('offer_id')}:{marker}")
            if not text.strip():
                failures.append(f"empty_clean:{row.get('offer_id')}")
        try:
            sections = json.loads((directory / "offer_sections.json").read_text(encoding="utf-8"))
            if not all(key in sections for key in ("offer_id", "sections", "source_files")):
                failures.append("sections_keys")
            section_data = sections.get("sections", {})
            if "główne cechy" in section_data.get("accessories", "").lower() or "opinie o produkcie" in section_data.get("accessories", "").lower():
                failures.append("invalid_accessories_section")
            if re.search(r"super sprzedawca|poleca\s+\d+[,.]\d+%|[a-z0-9_.-]+(?:_pl|-eu)", section_data.get("reviews", ""), re.I):
                failures.append("seller_info_in_reviews")
            if "## opis" in section_data.get("description", "").lower() and len(section_data.get("description", "").splitlines()) <= 1:
                failures.append("description_only_heading")
            if "specyfikacja" in clean.read_text(encoding="utf-8").lower() and len(section_data.get("technical_details", "").splitlines()) <= 1:
                failures.append("technical_details_only_heading")
            if "opinie" in clean.read_text(encoding="utf-8").lower() and not re.search(r"\d+[,.]\d+|ocen|recenz", section_data.get("reviews", ""), re.I):
                failures.append("reviews_without_rating_context")
            images = json.loads((directory / "product_images.json").read_text(encoding="utf-8"))
            if not isinstance(images.get("images"), list):
                failures.append("images_not_list")
            seller = json.loads((directory / "seller_info.json").read_text(encoding="utf-8"))
            if not all(key in seller for key in ("offer_id", "seller_name", "seller_rating", "seller_reviews_count", "seller_info_text", "source_quality_notes")):
                failures.append("seller_keys")
            source_markdown = (directory / "markdown.md").read_text(encoding="utf-8")
            if "super sprzedawca" in source_markdown.lower() and not (seller.get("seller_info_text") or seller.get("source_quality_notes")):
                failures.append("seller_info_not_extracted")
            seller_name = str(seller.get("seller_name", "")).replace("_", "\\_")
            if seller_name and any(line.strip() == seller_name for line in clean.read_text(encoding="utf-8").splitlines()):
                failures.append("seller_name_left_in_clean")
            summary = json.loads((directory / "technical_clean_summary.json").read_text(encoding="utf-8"))
            if "raw_markdown_chars" not in summary or "clean_markdown_chars" not in summary:
                failures.append("summary_keys")
            if summary.get("clean_markdown_chars", 0) <= 0:
                failures.append("summary_clean_empty")
        except (OSError, json.JSONDecodeError):
            failures.append(f"invalid_json:{row.get('offer_id')}")
    if failures:
        print("FAIL")
        print("\n".join(sorted(set(failures))))
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
