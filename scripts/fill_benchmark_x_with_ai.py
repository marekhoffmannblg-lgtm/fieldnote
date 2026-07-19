from __future__ import annotations

import argparse
import csv
import json
import os
import re
import urllib.request
from pathlib import Path

from build_benchmark_draft import BENCHMARK_FIELDS


ROOT_DIR = Path(__file__).resolve().parent.parent
CLEAN_PATH = ROOT_DIR / "output" / "benchmark_clean.csv"
FILLED_PATH = ROOT_DIR / "output" / "benchmark_ai_filled.csv"
SOURCES_PATH = ROOT_DIR / "output" / "benchmark_ai_filled_sources.csv"
PROMPTS_DIR = ROOT_DIR / "output" / "ai_x_prompts"
RESPONSES_DIR = ROOT_DIR / "output" / "ai_x_responses"
SOURCE_COLUMNS = ("offer_id", "detected_model", "field_name", "old_value", "new_value", "status", "confidence", "evidence", "normalized_url")
SYSTEM_PROMPT = """Jesteś ostrożnym ekstraktorem danych benchmarkowych. Nie zgaduj. Zwróć X, jeśli nie ma jasnego potwierdzenia. Używaj tylko treści aukcji. Nie używaj wiedzy ogólnej. Nie używaj internetu. Nie traktuj rekomendowanych produktów, altów ani linków do innych produktów jako danych analizowanej aukcji. Zwróć wyłącznie poprawny JSON zgodny z podanym schematem. Evidence maksymalnie 300 znaków."""
NOISE_SECTION_MARKERS = (
    "dbamy o twoją prywatność", "cookies", "podobne oferty", "sponsorowane",
    "sprzedający poleca", "inne oferty", "rekomendowane",
    "przewidywany przez allegro czas dostawy",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def markdown_for(offer_id: str, row: dict[str, str]) -> str:
    output_dir = row.get("output_dir", "")
    candidates = [ROOT_DIR / output_dir / "markdown.md", ROOT_DIR / "input" / "firecrawl_offer_pages" / offer_id / "markdown.md"]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def clean_markdown_for_ai(markdown_text: str, max_chars: int = 12000) -> str:
    """Keep product content and remove marketplace navigation/recommendations."""
    text = markdown_text.replace("\r\n", "\n")
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"https?://(?:a\.allegroimg\.com|allegro\.pl/events/clicks|allegro\.pl/dss-proxy/clicks)\S*", " ", text, flags=re.IGNORECASE)
    lines: list[str] = []
    for line in text.splitlines():
        lowered = line.strip().lower()
        if any(marker in lowered for marker in NOISE_SECTION_MARKERS):
            continue
        if "allegroimg" in lowered or "events/clicks" in lowered or "dss-proxy/clicks" in lowered:
            continue
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"https?://\S+", " ", line)
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    cleaned = "\n".join(lines).strip()
    return cleaned[:max_chars]


def prompt_for(row: dict[str, str], fields: list[str], markdown: str, max_chars: int) -> str:
    schema = {field: {"value": "X", "status": "still_x", "confidence": "high", "evidence": ""} for field in fields}
    cleaned_markdown = clean_markdown_for_ai(markdown, max_chars=max_chars)
    return f"""{SYSTEM_PROMPT}

Tekst aukcji został oczyszczony z rekomendacji i linków technicznych.

Oferta offer_id: {row.get('offer_id', '')}
Model pomocniczy: {row.get('detected_model', '')}

Analizuj tylko te pola, które mają X:
{json.dumps(fields, ensure_ascii=False)}

Treść lokalnego markdown.md aukcji:
---
{cleaned_markdown}
---

Zwróć JSON w formacie:
{json.dumps({'offer_id': row.get('offer_id', ''), 'fields': schema}, ensure_ascii=False)}
"""


def call_openai(prompt: str, api_key: str) -> dict[str, object]:
    payload = {"model": "gpt-4o-mini", "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]}
    request = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-chars", type=int, default=12000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not CLEAN_PATH.exists():
        print("Brak output/benchmark_clean.csv")
        return 1
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key and not args.dry_run:
        print("Brak OPENAI_API_KEY. Ustaw klucz albo uruchom z --dry-run.")
        return 1

    rows = read_csv(CLEAN_PATH)
    rows_to_process = rows[: args.limit] if args.limit > 0 else rows
    filled_rows = [dict(row) for row in rows]
    sources: list[dict[str, str]] = []
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    for old_prompt in PROMPTS_DIR.glob("*.txt"):
        old_prompt.unlink()
    if not args.dry_run:
        RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(rows_to_process):
        fields = [field for field in BENCHMARK_FIELDS if row.get(field, "") == "X"]
        markdown = markdown_for(row.get("offer_id", ""), row)
        prompt = prompt_for(row, fields, markdown, max_chars=max(1, args.max_chars))
        prompt_path = PROMPTS_DIR / f"{row.get('offer_id') or index}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        result = {"offer_id": row.get("offer_id", ""), "fields": {}}
        if not args.dry_run:
            try:
                result = call_openai(prompt, api_key)
                (RESPONSES_DIR / f"{row.get('offer_id') or index}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as error:
                result = {"offer_id": row.get("offer_id", ""), "fields": {}}
                print(f"Błąd dla {row.get('offer_id', '')}: {error}")
        result_fields = result.get("fields", {}) if isinstance(result, dict) else {}
        for field in fields:
            item = result_fields.get(field, {}) if isinstance(result_fields, dict) else {}
            value = str(item.get("value", "X")).strip() if isinstance(item, dict) else "X"
            evidence = str(item.get("evidence", ""))[:300] if isinstance(item, dict) else ""
            status = str(item.get("status", "still_x")) if isinstance(item, dict) else "still_x"
            confidence = str(item.get("confidence", "")) if isinstance(item, dict) else ""
            if value != "X" and status == "filled" and evidence:
                filled_rows[rows.index(row)][field] = value
            else:
                value, status = "X", "still_x" if args.dry_run or not evidence else "unclear"
            sources.append({"offer_id": row.get("offer_id", ""), "detected_model": row.get("detected_model", ""), "field_name": field, "old_value": "X", "new_value": value, "status": status, "confidence": confidence, "evidence": evidence, "normalized_url": row.get("normalized_url", "")})

    with FILLED_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader(); writer.writerows(filled_rows)
    with SOURCES_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_COLUMNS)
        writer.writeheader(); writer.writerows(sources)
    print(f"benchmark_ai_filled_rows={len(filled_rows)} sources={len(sources)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
