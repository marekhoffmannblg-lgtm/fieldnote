from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
AUDIT_PATH = ROOT_DIR / "output" / "offer_page_field_audit.csv"
QUEUE_PATH = ROOT_DIR / "output" / "firecrawl_offer_queue.csv"
TARGET_FIELDS = (
    "Auto-folding",
    "Regulacja rączki",
    "Hamulec",
    "Wodoodporna budka",
    "Wymiary oparcia / miejsce do spania",
)
NEGATIVE_PHRASES = (
    "brak",
    "bez",
    "nie",
    "stała rączka",
    "rączka stała",
    "parasolka",
    "składanie parasolkowe",
    "bez amortyzacji",
    "brak amortyzacji",
)


def load_rows() -> list[dict[str, str]]:
    with AUDIT_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def print_counts(rows: list[dict[str, str]]) -> None:
    counts = Counter(row.get("value_type", "") or "empty" for row in rows)
    print("\nŁączna liczba rekordów według value_type:")
    for value_type in ("positive", "negative", "unknown", "empty"):
        print(f"- {value_type}: {counts[value_type]}")

    by_field: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_field[row.get("field_name", "")][row.get("value_type", "") or "empty"] += 1
    print("\nvalue_type per field_name:")
    for field_name in sorted(by_field):
        values = by_field[field_name]
        print(
            f"- {field_name}: positive={values['positive']} "
            f"negative={values['negative']} unknown={values['unknown']} empty={values['empty']}"
        )


def print_field_examples(rows: list[dict[str, str]]) -> None:
    print("\nPrzykłady dla wybranych pól:")
    for field_name in TARGET_FIELDS:
        print(f"\n[{field_name}]")
        examples = [row for row in rows if row.get("field_name") == field_name][:10]
        if not examples:
            print("brak rekordów")
            continue
        for row in examples:
            print(
                f"offer_id={row.get('offer_id', '')} | "
                f"model={row.get('detected_model', '')} | "
                f"field={row.get('field_name', '')} | found={row.get('found', '')} | "
                f"value_type={row.get('value_type', '') or 'empty'} | "
                f"confidence={row.get('confidence', '')} | "
                f"evidence={row.get('evidence', '')}"
            )


def load_markdowns() -> dict[str, tuple[str, str]]:
    if not QUEUE_PATH.exists():
        return {}
    with QUEUE_PATH.open(encoding="utf-8", newline="") as handle:
        queue_rows = list(csv.DictReader(handle))
    markdowns: dict[str, tuple[str, str]] = {}
    for row in queue_rows:
        offer_id = row.get("offer_id", "")
        output_dir = row.get("output_dir", "")
        if not offer_id or not output_dir:
            continue
        markdown_path = ROOT_DIR / output_dir / "markdown.md"
        if markdown_path.is_file():
            markdowns[offer_id] = (row.get("detected_model", ""), markdown_path.read_text(encoding="utf-8", errors="replace"))
    return markdowns


def print_negative_matches(rows: list[dict[str, str]]) -> None:
    matches: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        evidence = row.get("evidence", "").lower()
        for phrase in NEGATIVE_PHRASES:
            if phrase in evidence:
                matches[phrase].add((row.get("offer_id", ""), row.get("detected_model", "")))

    for offer_id, (model, markdown) in load_markdowns().items():
        lowered = markdown.lower()
        for phrase in NEGATIVE_PHRASES:
            if phrase in lowered:
                matches[phrase].add((offer_id, model))

    print("\nFrazy negatywne w evidence i markdownach:")
    for phrase in NEGATIVE_PHRASES:
        found = sorted(matches[phrase])
        if found:
            formatted = ", ".join(f"{offer_id}/{model}" for offer_id, model in found)
            print(f"- {phrase}: {formatted}")
        else:
            print(f"- {phrase}: brak")


def main() -> int:
    if not AUDIT_PATH.exists():
        print("Najpierw uruchom: python3 scripts/audit_offer_page_fields.py")
        return 0
    rows = load_rows()
    print_counts(rows)
    print_field_examples(rows)
    print_negative_matches(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
