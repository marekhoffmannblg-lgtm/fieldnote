from __future__ import annotations

import argparse
import csv
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "output" / "firecrawl_offer_queue.csv"
PAGES = ROOT / "input" / "firecrawl_offer_pages"
PROMPTS = ROOT / "output" / "ai_extractor_prompts"

BENCHMARK_FIELDS = ("Marka", "Model", "Status", "Rama", "Koła", "Udźwig", "Regulacja oparcia", "Auto-folding", "Składanie jedną ręką", "Waga", "Wymiary po złożeniu", "Siedzisko", "Amortyzacja", "Koła 360°", "Hamulec", "Budka XXL", "Filtr UPF50+", "Wodoodporna budka", "Regulacja rączki", "Wymiary oparcia / miejsce do spania", "Akcesoria")
SYSTEM_RULES = "Nie zgaduj. Nie używaj wiedzy ogólnej. X oznacza brak potwierdzenia w aukcji. detected_brand można użyć do pola Marka, a detected_model można użyć do pola Model; detected_title można użyć jako evidence dla Marka/Model, jeśli zawiera markę/model. Opinie mają trafić tylko do reviews_summary. Dane sprzedawcy mają trafić tylko do source_quality. Dane zdjęć mają trafić tylko do product_images. product_images MUSI być listą obiektów, nie listą stringów; każdy obiekt musi mieć image_url, alt_text i is_primary_candidate. Benchmark fields nie mogą zawierać opinii, danych sprzedawcy, dostawy, podobnych ofert ani sponsorowanych produktów."


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def prompt_for(row: dict[str, str], sections: dict, images: dict, seller: dict) -> str:
    image_rows = [image for image in images.get("images", []) if image.get("is_likely_product_image")]
    def image_rank(image: dict) -> tuple[int, int]:
        url = str(image.get("image_url", "")).lower()
        return (0 if "original" in url else 1 if "s720" in url else 2, 1 if "s128" in url else 0)
    image_rows.sort(key=image_rank)
    candidates = image_rows[:3]
    payload = {
        "offer_id": row.get("offer_id", ""), "source_url": sections.get("source_url", row.get("normalized_url", "")),
        "detected_title": sections.get("detected_title", ""), "detected_brand": sections.get("detected_brand", row.get("brand", "")),
        "detected_model": sections.get("detected_model", row.get("detected_model", "")), "price": sections.get("price", ""),
        "sections": {key: sections.get("sections", {}).get(key, "") for key in ("parameters", "description", "features", "technical_details", "accessories", "reviews")},
        "product_images": {"primary_image_candidate": candidates[0] if candidates else {}, "images_count": len(image_rows), "image_candidates": candidates},
    }
    mapping = {
        "Rama": "Rama, stelaż, konstrukcja, aluminium/stal", "Koła": "Koła, EVA, pianka, średnica kół", "Udźwig": "maksymalne obciążenie, do 22 kg, do 25 kg", "Regulacja oparcia": "oparcie, regulacja oparcia, pozycja leżąca", "Składanie jedną ręką": "jedną ręką, CLICK & FOLD", "Waga": "Waga produktu, Waga, kg", "Wymiary po złożeniu": "Wymiary po złożeniu", "Siedzisko": "siedzisko, podnóżek, pozycja leżąca", "Amortyzacja": "amortyzacja, amortyzowane", "Koła 360°": "360°, obracają się o 360", "Hamulec": "hamulec", "Budka XXL": "duża budka, poszerzana budka, budka XXL, budka XL", "Filtr UPF50+": "UPF50, UPF 50", "Wodoodporna budka": "wodoodporna budka, wodoodporny materiał", "Regulacja rączki": "regulowana rączka, wysokość rączki", "Akcesoria": "W zestawie, Akcesoria, Zestaw zawiera",
    }
    output_schema = {"offer_id": "...", "source_url": "...", "detected_title": "...", "detected_brand": "...", "detected_model": "...", "price": "...", "fields": "obiekt z każdym wymaganym polem", "reviews_summary": {"rating": "", "reviews_count": "", "summary": "", "pros": [], "cons": [], "evidence": ""}, "source_quality": {"seller_name": "", "seller_rating": "", "seller_reviews_count": "", "notes": []}, "product_images": [{"image_url": "...", "alt_text": "...", "is_primary_candidate": False}], "warnings": []}
    return f"""Jesteś ostrożnym ekstraktorem faktów z jednej lokalnej karty aukcji. {SYSTEM_RULES}
Najpierw aktywnie sprawdź każde pole w sections.parameters, sections.description, sections.technical_details i sections.accessories. Nie zostawiaj X, jeśli w danych źródłowych jest literalne potwierdzenie.
Jeśli literalny fragment istnieje, pole nie może zostać X. Przykładowo: "Rama: aluminium" oznacza, że Rama nie może być X; "Waga produktu: 5,9 kg" oznacza, że Waga nie może być X; "Budka: UPF50+, wodoodporna" oznacza, że Filtr UPF50+ i Wodoodporna budka nie mogą być X.

Wymagane pola:
{json.dumps(BENCHMARK_FIELDS, ensure_ascii=False)}

Mapowanie pól i terminów do sprawdzenia:
{json.dumps(mapping, ensure_ascii=False, indent=2)}

Każde pole ma format:
{{"value": "wartość albo X", "status": "confirmed|not_found|unclear", "confidence": "high|medium|low", "evidence": "krótki cytat max 300 znaków"}}

Przykład confirmed:
"Rama": {{"value": "aluminium", "status": "confirmed", "confidence": "high", "evidence": "Rama: aluminium"}}

Przykład not_found:
"Hamulec": {{"value": "X", "status": "not_found", "confidence": "high", "evidence": ""}}

Dane źródłowe aukcji:
---
{json.dumps(payload, ensure_ascii=False, indent=2)[:16000]}
---

Schema JSON odpowiedzi:
{json.dumps(output_schema, ensure_ascii=False, indent=2)}
"""


def call_api(prompt: str, key: str, model: str) -> dict:
    body = {"model": model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": SYSTEM_RULES}, {"role": "user", "content": prompt}]}
    request = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode())
    return json.loads(result["choices"][0]["message"]["content"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model", default="gpt-4.1-nano")
    parser.add_argument("--max-input-chars", type=int, default=16000)
    args = parser.parse_args()
    key = os.environ.get("OPENAI_API_KEY", "")
    if not args.dry_run and not key:
        print("Brak OPENAI_API_KEY. Ustaw zmienną środowiskową albo użyj --dry-run.")
        return 1
    with QUEUE.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("status", "").lower() == "fetched"]
    if args.limit:
        rows = rows[:max(0, args.limit)]
    PROMPTS.mkdir(parents=True, exist_ok=True)
    written = 0
    for row in rows:
        offer_id = row.get("offer_id", "")
        directory = PAGES / offer_id
        sections = read_json(directory / "offer_sections.json")
        images = read_json(directory / "product_images.json")
        seller = read_json(directory / "seller_info.json")
        prompt = prompt_for(row, sections, images, seller)
        prompt_path = PROMPTS / f"{offer_id}.txt"
        if args.force or not prompt_path.exists():
            prompt_path.write_text(prompt[:args.max_input_chars + 12000], encoding="utf-8")
            written += 1
        if not args.dry_run:
            output_path = directory / "product_facts_ai.json"
            if output_path.exists() and not args.force:
                continue
            output_path.write_text(json.dumps(call_api(prompt, key, args.model), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"prompts_written={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
