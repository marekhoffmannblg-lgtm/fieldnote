from __future__ import annotations

import csv
import re
from pathlib import Path

from build_benchmark_draft import BENCHMARK_FIELDS


ROOT_DIR = Path(__file__).resolve().parent.parent
DRAFT_PATH = ROOT_DIR / "output" / "benchmark_draft.csv"
SOURCES_PATH = ROOT_DIR / "output" / "benchmark_sources.csv"
CLEAN_PATH = ROOT_DIR / "output" / "benchmark_clean.csv"
CLEAN_SOURCES_PATH = ROOT_DIR / "output" / "benchmark_clean_sources.csv"
BASE_COLUMNS = ("brand", "category", "detected_model", "offer_id", "normalized_url")
CLEAN_COLUMNS = (*BASE_COLUMNS, *BENCHMARK_FIELDS)
SOURCE_COLUMNS = ("offer_id", "detected_model", "field_name", "clean_value", "evidence", "confidence", "normalized_url", "clean_status")
NOISE_MARKERS = ("https://", "http://", "![", "](", "allegroimg", "s480", "original/", "sprzedający poleca", "podobne produkty", "inne oferty", "rekomendowane", "sponsorowane", "rowerek biegowy", "torba do wózka", "fotelik samochodowy", "lionelo")
HARD_NOISE_MARKERS = (*NOISE_MARKERS, "doręczenia przez przewoźnika", "sprzedającego oraz czasu", "przejdź do treści")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def clean_evidence_text(text: str) -> str:
    text = " ".join(text.split())
    # Zachowaj opis przed dołączonym obrazkiem/linkiem, ale nie używaj samego linku.
    cut_positions = [position for marker in ("![", "](", "https://", "http://") if (position := text.lower().find(marker)) >= 0]
    if cut_positions:
        text = text[: min(cut_positions)].strip()
    lowered = text.lower()
    if not text or any(marker in lowered for marker in HARD_NOISE_MARKERS if marker not in {"https://", "http://", "![", "]("}):
        return ""
    return text


def is_relevant_clean_value(text: str, field_name: str) -> bool:
    lowered = text.lower()
    if not text or len(text) > 160 or any(marker in lowered for marker in HARD_NOISE_MARKERS):
        return False
    if any(marker in lowered for marker in ("https://", "http://", "![", "](", "allegroimg")):
        return False
    strict_context = {
        "Siedzisko": ("siedzisko", "oparcie", "podnóżek", "pozycja leżąca", "od urodzenia", "od 6 miesięcy"),
        "Amortyzacja": ("amortyzacja", "amortyzowane koła", "amortyzowane"),
        "Budka XXL": ("budka",),
    }
    allowed = strict_context.get(field_name)
    if allowed and not any(token in lowered for token in allowed):
        return False
    # A clean value must contain a parameter cue, not a delivery/recommendation fragment.
    if field_name in {"Siedzisko", "Amortyzacja", "Budka XXL"} and len(text.split()) < 1:
        return False
    return True


def shorten_evidence(evidence: str, field_name: str, value_type: str) -> str:
    text = clean_evidence_text(evidence)
    if not text:
        return ""
    if value_type == "negative":
        match = re.search(r"(?:brak|bez) [^.!,;]{0,80}|(?:rączka stała|stała rączka)", text, re.IGNORECASE)
        return f"nie / brak — {match.group(0).strip()}"[:160] if match else f"nie / brak — {text[:140]}"

    patterns = {
        "Waga": r"\b\d+(?:[,.]\d+)?\s*kg\b",
        "Udźwig": r"\b(?:do\s+\d+(?:[,.]\d+)?\s*kg|maksymalne obciążenie\s+\d+(?:[,.]\d+)?\s*kg|obciążenie do\s+\d+(?:[,.]\d+)?\s*kg|udźwig\s+\d+(?:[,.]\d+)?\s*kg)\b",
        "Wymiary po złożeniu": r"\b\d+(?:[,.]\d+)?\s*[×x]\s*\d+(?:[,.]\d+)?(?:\s*[×x]\s*\d+(?:[,.]\d+)?)?\s*cm\b",
        "Wymiary oparcia / miejsce do spania": r"\b\d+(?:[,.]\d+)?\s*[×x]\s*\d+(?:[,.]\d+)?\s*cm\b|\bdługość leżenia\s*:?\s*\d+(?:[,.]\d+)?\s*cm\b",
        "Filtr UPF50+": r"\bUPF\s*50\+?\b|\bUPF50\+\b",
        "Koła": r"\b(?:EVA|PU)\b|\bpiankowe\b|\bgumowe\b",
        "Koła 360°": r"\b(?:koła\s*)?360\s*°?\b",
    }
    if field_name == "Waga" and re.search(r"udźwig|obciążenie|do\s+\d+(?:[,.]\d+)?\s*kg", text, re.IGNORECASE):
        return ""
    pattern = patterns.get(field_name)
    if pattern:
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(0).strip()[:160] if match else ""
    strict_patterns = {
        "Rama": r"\b(?:aluminium|stal)\b",
        "Koła": r"\b(?:EVA|PU|piankowe|gumowe|nieprzebijalne|amortyzowane)\b|przednie\s+360\s*°?|średnica kół",
        "Akcesoria": r"\b(?:folia|moskitiera|uchwyt na kubek|adaptery?|torba|pokrowiec|pałąk|tacka|kosz|pasek na ramię)\b",
        "Filtr UPF50+": r"\b(?:UPF\s*50\+?|UV)\b",
        "Wodoodporna budka": r"\b(?:wodoodporna|wodoodporny)\b[^.!?;]{0,35}\bbudka\b|\bbudka\b[^.!?;]{0,35}\b(?:wodoodporna|wodoodporny)\b",
        "Hamulec": r"\b(?:STOP\s*&\s*RIDE|hamulec nożny|centralny hamulec|hamulec postojowy|hamulec tylny)\b",
        "Regulacja rączki": r"\b(?:regulowana rączka|regulacja rączki|regulowana wysokość rączki)\b",
        "Koła 360°": r"\b(?:przednie\s+)?360\s*°\b",
    }
    strict = strict_patterns.get(field_name)
    if strict:
        match = re.search(strict, text, re.IGNORECASE)
        return match.group(0).strip()[:160] if match else ""
    for keyword in ("automatyczne składanie", "auto folding", "jedną ręką", "siedzisko", "amortyzacja", "budka"):
        match = re.search(rf"[^.!?;]{{0,35}}{re.escape(keyword)}[^.!?;]{{0,55}}", text, re.IGNORECASE)
        if match:
            return " ".join(match.group(0).split())[:160]
    return text[:120] if not any(marker in text.lower() for marker in NOISE_MARKERS) else ""


def build_outputs() -> tuple[int, int]:
    draft_rows = read_csv(DRAFT_PATH)
    source_rows = read_csv(SOURCES_PATH)
    sources_by_key = {(row.get("offer_id", ""), row.get("field_name", "")): row for row in source_rows if row.get("evidence")}
    clean_rows: list[dict[str, str]] = []
    clean_sources: list[dict[str, str]] = []
    for draft in draft_rows:
        clean = {column: draft.get(column, "") for column in BASE_COLUMNS}
        for field_name in BENCHMARK_FIELDS:
            source = sources_by_key.get((draft.get("offer_id", ""), field_name))
            if source and source.get("value_type") in {"positive", "negative"}:
                value = shorten_evidence(source.get("evidence", ""), field_name, source.get("value_type", ""))
                clean_value = value if is_relevant_clean_value(value, field_name) else "X"
                clean[field_name] = clean_value
                clean_sources.append({
                    "offer_id": draft.get("offer_id", ""),
                    "detected_model": draft.get("detected_model", ""),
                    "field_name": field_name,
                    "clean_value": clean_value,
                    "evidence": source.get("evidence", ""),
                    "confidence": source.get("confidence", ""),
                    "normalized_url": draft.get("normalized_url", ""),
                    "clean_status": "extracted" if clean_value != "X" else "rejected_noise",
                })
            else:
                clean[field_name] = "X"
                clean_sources.append({
                    "offer_id": draft.get("offer_id", ""),
                    "detected_model": draft.get("detected_model", ""),
                    "field_name": field_name,
                    "clean_value": "X",
                    "evidence": source.get("evidence", "") if source else "",
                    "confidence": source.get("confidence", "") if source else "",
                    "normalized_url": draft.get("normalized_url", ""),
                    "clean_status": "x_missing" if not source else "rejected_noise",
                })
        clean_rows.append(clean)

    CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CLEAN_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLEAN_COLUMNS)
        writer.writeheader()
        writer.writerows(clean_rows)
    with CLEAN_SOURCES_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_COLUMNS)
        writer.writeheader()
        writer.writerows(clean_sources)
    return len(clean_rows), len(clean_sources)


if __name__ == "__main__":
    rows, sources = build_outputs()
    print(f"clean_rows={rows} clean_sources={sources}")
