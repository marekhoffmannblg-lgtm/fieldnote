from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from run_context import load_offer_ids, normalized_offer_ids
from p0_runtime import atomic_write_bundle


ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "output" / "firecrawl_offer_queue.csv"
PAGES = ROOT / "input" / "firecrawl_offer_pages"

NOISE_HEADINGS = (
    "dbamy o twoją prywatność", "podobne oferty", "sponsorowane", "rekomendowane",
    "inne oferty", "inne aukcje", "przewidywany przez allegro czas dostawy",
    "dostawa i zwroty", "dostawa", "zwroty", "polityka prywatności", "cookies",
)
NOISE_MARKERS = (
    "events/clicks", "dss-proxy/clicks", "a.allegroimg.com", "sprzedający poleca",
    "podobne produkty", "rekomendowane produkty", "inne aukcje sprzedającego",
    "przewidywany przez allegro czas dostawy", "przejdź do treści",
)
HARD_CUTOFFS = {
    "zamów zestaw w jednej przesyłce": "zamow_zestaw",
    "propozycje dla ciebie": "propozycje_dla_ciebie",
    "warunki oferty": "warunki_oferty",
    "opcje zakupu": "opcje_zakupu",
    "przewidywana dostawa": "przewidywana_dostawa",
    "przewidywany przez allegro czas dostawy": "przewidywana_dostawa",
    "pokaż warianty od innych sprzedających": "inne_warianty",
    "porównaj": "porownaj",
    "co sądzisz o tej stronie?": "ankieta_strony",
    "masz firmę? weź w leasing": "leasing",
    "dodaj do koszyka": "opcje_zakupu",
    "kup i zapłać": "opcje_zakupu",
}
SECTION_ALIASES = {
    "parameters": ("parametry", "marka:", "stan:"),
    "description": ("opis", "opis produktu"),
    "features": ("cechy", "zalety", "najważniejsze cechy"),
    "technical_details": ("dane techniczne", "specyfikacja", "specyfikacja techniczna"),
    "accessories": ("akcesoria", "w zestawie", "zawartość zestawu"),
    "reviews": ("opinie", "oceny", "recenzje"),
}


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def clean_line(line: str) -> str:
    line = re.sub(r"!\[[^]]*\]\([^)]*\)", "", line)
    line = re.sub(r"https?://\S+", "", line)
    line = re.sub(r"\[[^]]+\]\([^)]*\)", "", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line


def clean_markdown(markdown: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    output: list[str] = []
    skip = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        low = line.lower()
        heading = re.sub(r"^#+\s*", "", low).strip()
        cutoff = next((marker for marker, marker_name in HARD_CUTOFFS.items() if heading.startswith(marker)), None)
        if cutoff and HARD_CUTOFFS[cutoff] in {"propozycje_dla_ciebie", "przewidywana_dostawa", "zamow_zestaw"}:
            skip = True
            removed.append(HARD_CUTOFFS[cutoff])
            continue
        if cutoff and (line.startswith("#") or HARD_CUTOFFS[cutoff] not in {"opcje_zakupu"}):
            removed.append(HARD_CUTOFFS[cutoff])
            break
        if cutoff and HARD_CUTOFFS[cutoff] == "opcje_zakupu":
            removed.append("opcje_zakupu")
            continue
        if "co sądzisz o tej stronie?" in low:
            removed.append("ankieta_strony")
            continue
        if low in {"zamknij", "dodaj zestaw do koszyka"} or re.match(r"^cena za \d+\s+produkt", low):
            removed.append("zakupowe_ui")
            continue
        if line.startswith("### Parametry"):
            removed.append("drugi_naglowek_parametrow")
            continue
        if any(heading.startswith(marker) for marker in NOISE_HEADINGS):
            skip = True
            removed.append(heading[:80])
            continue
        if skip and line.startswith("#"):
            skip = False
        if skip:
            continue
        if any(marker in low for marker in NOISE_MARKERS):
            removed.append(next(marker for marker in NOISE_MARKERS if marker in low))
            continue
        cleaned = clean_line(raw_line)
        if re.match(r"^\[[^]]+\]\(", raw_line.strip()) or "](" in cleaned:
            removed.append("technical_link")
            continue
        if re.fullmatch(r"[A-Za-z0-9_.-]+_pl", cleaned.replace("\\_", "_")):
            removed.append("seller_info_extracted")
            continue
        if re.search(r"sprzedawc|poleca\s+\d+[,.]\d+%|super sprzedawca", cleaned, re.I):
            removed.append("seller_info_extracted")
            continue
        if not cleaned or cleaned == "|":
            continue
        output.append(cleaned)

    deduped: list[str] = []
    seen: set[str] = set()
    for line in output:
        key = re.sub(r"\s+", " ", line).strip().lower()
        if key not in seen:
            seen.add(key)
            deduped.append(line)
    return "\n".join(deduped).strip() + "\n", sorted(set(removed))


def extract_images(markdown: str, html: str, title: str, brand: str, model: str, offer_id: str) -> dict:
    boundary = re.search(r"##\s*(podobne oferty|sponsorowane|rekomendowane|inne oferty)", markdown, re.I)
    source = markdown[:boundary.start()] if boundary else markdown
    found = re.findall(r"!\[([^]]*)\]\((https?://[^)]+)\)", source)
    if not found:
        found = re.findall(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*alt=["\']([^"\']*)["\']', html, re.I)
        found = [(alt, url) for url, alt in found]
    wanted = {word.lower() for word in re.findall(r"[\wÀ-ž]+", f"{title} {brand} {model}") if len(word) > 2}
    images = []
    seen = set()
    for alt, url in found:
        if url in seen or "allegroimg" not in url.lower():
            continue
        seen.add(url)
        alt_words = set(re.findall(r"[\wÀ-ž]+", alt.lower()))
        likely = bool(wanted & alt_words) and offer_id not in url
        if likely:
            images.append({"image_url": url, "alt_text": alt, "is_likely_product_image": True, "reason": "alt zawiera tytuł, markę lub model oferty"})
    return {"offer_id": offer_id, "images": images}


def heading_ranges(cleaned: str) -> list[tuple[int, str]]:
    return [(index, re.sub(r"^##\s*", "", line).strip().lower())
            for index, line in enumerate(cleaned.splitlines()) if line.startswith("## ")]


def section_between(cleaned: str, start_names: tuple[str, ...], end_names: tuple[str, ...] = ()) -> str:
    lines = cleaned.splitlines()
    ranges = heading_ranges(cleaned)
    start = next(((index, name) for index, name in ranges if any(alias in name for alias in start_names)), None)
    if not start:
        return ""
    end_index = len(lines)
    for index, name in ranges:
        if index > start[0] and any(alias in name for alias in end_names):
            end_index = index
            break
    if end_names:
        for index in range(start[0] + 1, len(lines)):
            if not lines[index].startswith("#"):
                continue
            heading = re.sub(r"^#+\s*", "", lines[index]).strip().lower()
            if any(alias in heading for alias in end_names):
                end_index = min(end_index, index)
                break
    return "\n".join(lines[start[0]:end_index]).strip()


def section_text(cleaned: str, aliases: tuple[str, ...]) -> str:
    return section_between(cleaned, aliases)


def clean_reviews(text: str) -> str:
    lines = []
    for line in text.splitlines():
        value = line.strip()
        normalized = value.replace("\\_", "_")
        if re.fullmatch(r"[A-Za-z0-9_.-]+(?:_pl|-eu)", normalized):
            break
        if re.search(r"super sprzedawca|poleca\s+\d+[,.]\d+%", value, re.I):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def extract_seller(markdown: str, offer_id: str) -> dict:
    seller_name = ""
    match = re.search(r"(?:użytkownik|sprzedawcy/)(?:/|%2F)([A-Za-z0-9_.-]+)", markdown, re.I)
    if not match:
        match = re.search(r"logo\s+([A-Za-z0-9_.-]+)", markdown, re.I)
    if match:
        seller_name = match.group(1)
    rating = ""
    rating_match = re.search(r"poleca\s+(\d+[,.]\d+%)", markdown, re.I)
    if rating_match:
        rating = rating_match.group(1)
    seller_lines = [line.strip() for line in markdown.splitlines() if re.search(r"sprzedawc|poleca\s+\d+[,.]\d+%|super sprzedawca", line, re.I)]
    return {"offer_id": offer_id, "seller_name": seller_name, "seller_rating": rating, "seller_reviews_count": "", "seller_info_text": "\n".join(seller_lines), "source_quality_notes": (["Super Sprzedawca"] if re.search(r"super sprzedawca", markdown, re.I) else [])}


def process(row: dict[str, str], force: bool) -> bool:
    offer_id = str(row.get("offer_id", "")).strip()
    if not offer_id:
        return False
    directory = PAGES / offer_id
    outputs = [directory / name for name in ("technical_clean.md", "offer_sections.json", "product_images.json", "seller_info.json", "technical_clean_summary.json")]
    if not force and all(path.exists() for path in outputs):
        return False
    markdown_path = directory / "markdown.md"
    if not markdown_path.exists():
        print(f"WARNING: brak markdown.md dla {offer_id}")
        return False
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
    html = (directory / "html.html").read_text(encoding="utf-8", errors="replace") if (directory / "html.html").exists() else ""
    metadata = read_json(directory / "metadata.json")
    title = str(metadata.get("og:title") or metadata.get("ogTitle") or row.get("detected_model", ""))
    source_url = str(metadata.get("sourceURL") or metadata.get("url") or row.get("normalized_url", ""))
    cleaned, removed = clean_markdown(markdown)
    sections = {name: section_text(cleaned, aliases) for name, aliases in SECTION_ALIASES.items()}
    sections["parameters"] = section_between(cleaned, ("parametry",), ("opis", "specyfikacja", "opinie"))
    sections["description"] = section_between(cleaned, ("opis",), ("specyfikacja", "opinie"))
    sections["technical_details"] = section_between(cleaned, ("specyfikacja", "dane techniczne"), ("opinie",))
    sections["reviews"] = clean_reviews(section_between(cleaned, ("opinie o produkcie", "opinie", "recenzje")))
    sections["accessories"] = section_between(cleaned, ("w zestawie", "akcesoria", "zestaw zawiera"), ("główne cechy", "cechy", "opinie o produkcie", "specyfikacja"))
    feature_heads = ("składanie jedną ręką", "duże, regulowane siedzisko", "idealny na wakacje", "zwrotny i niezawodny", "pozycja leżąca", "rozkładana budka", "koła bez pompowania")
    sections["features"] = "\n".join(
        line for line in sections["description"].splitlines()
        if any(token in line.lower() for token in feature_heads)
    )
    sections["title"] = title if title else (cleaned.splitlines()[0] if cleaned else "")
    price_match = re.search(r"\b\d+[,.]\d{2}\s*(?:zł|PLN)", cleaned, re.I) or re.search(r"\b\d+[,.]\d{2}\s*(?:zł|PLN)", markdown, re.I)
    sections["price"] = price_match.group(0) if price_match else ""
    image_data = extract_images(markdown, html, title, "Kinderkraft", row.get("detected_model", ""), offer_id)
    seller = extract_seller(markdown, offer_id)
    if not seller["seller_info_text"]:
        seller["source_quality_notes"].append("Nie znaleziono jednoznacznych danych sprzedawcy w oczyszczonym markdownie.")
    if seller["seller_info_text"]:
        removed.append("seller_info_extracted")
    summary = {"offer_id": offer_id, "raw_markdown_chars": len(markdown), "clean_markdown_chars": len(cleaned), "removed_noise_markers": sorted(set(removed)), "sections_found": [key for key, value in sections.items() if value], "images_count": len(image_data["images"]), "seller_info_found": bool(seller["seller_info_text"]), "warnings": []}
    if not cleaned:
        summary["warnings"].append("Oczyszczony markdown jest pusty.")
    atomic_write_bundle(
        directory,
        {
            "technical_clean.md": cleaned,
            "offer_sections.json": json.dumps({"offer_id": offer_id, "source_url": source_url, "detected_title": title, "detected_brand": "Kinderkraft", "detected_model": row.get("detected_model", ""), "price": sections["price"], "sections": sections, "source_files": {"markdown": "markdown.md", "html": "html.html", "links": "links.txt", "metadata": "metadata.json"}}, ensure_ascii=False, indent=2),
            "product_images.json": json.dumps(image_data, ensure_ascii=False, indent=2),
            "seller_info.json": json.dumps(seller, ensure_ascii=False, indent=2),
            "technical_clean_summary.json": json.dumps(summary, ensure_ascii=False, indent=2),
        },
        json_files={"offer_sections.json", "product_images.json", "seller_info.json", "technical_clean_summary.json"},
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--offer-id", action="append", default=[], help="Czyści wyłącznie wskazaną ofertę; opcję można powtórzyć.")
    parser.add_argument("--offer-ids-file", help="JSON/CSV/tekst z offer_id; w kontekście pipeline używa fetched_offer_ids.")
    args = parser.parse_args()
    if not QUEUE.exists():
        print(f"Brak pliku: {QUEUE}")
        return 1
    with QUEUE.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("status", "").lower() == "fetched"]
    selected_offer_ids = normalized_offer_ids(args.offer_id)
    if args.offer_ids_file:
        try:
            selected_offer_ids.update(load_offer_ids(args.offer_ids_file))
        except (OSError, ValueError) as exc:
            print(f"Błąd odczytu --offer-ids-file: {exc}")
            return 1
    if selected_offer_ids:
        rows = [row for row in rows if row.get("offer_id", "") in selected_offer_ids]
    if args.limit is not None:
        rows = rows[: max(0, args.limit)]
    processed = sum(process(row, args.force) for row in rows)
    print(f"fetched={len(rows)} processed={processed}")
    print(f"offers_cleaned={processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
