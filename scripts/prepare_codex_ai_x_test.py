from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CLEAN_PATH = ROOT_DIR / "output" / "benchmark_clean.csv"
QUEUE_PATH = ROOT_DIR / "output" / "firecrawl_offer_queue.csv"
TEST_DIR = ROOT_DIR / "output" / "codex_ai_x_test"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if not CLEAN_PATH.exists():
        print("Brak output/benchmark_clean.csv")
        return 1
    rows = read_csv(CLEAN_PATH)
    samples = [row for row in rows if any(value == "X" for key, value in row.items() if key not in {"brand", "category", "detected_model", "offer_id", "normalized_url"})]
    samples = samples[: max(0, args.limit)]
    queue = {row.get("offer_id", ""): row for row in read_csv(QUEUE_PATH)} if QUEUE_PATH.exists() else {}
    offer_dir = TEST_DIR / "offer_pages"
    offer_dir.mkdir(parents=True, exist_ok=True)
    for old in offer_dir.glob("*.md"):
        old.unlink()
    with (TEST_DIR / "benchmark_x_sample.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader(); writer.writerows(samples)
    for row in samples:
        offer_id = row.get("offer_id", "")
        output_dir = queue.get(offer_id, {}).get("output_dir", "")
        source_dir = Path(output_dir)
        if not source_dir.is_absolute():
            source_dir = ROOT_DIR / source_dir
        markdown = source_dir / "markdown.md"
        if markdown.is_file():
            shutil.copyfile(markdown, offer_dir / f"{offer_id}.md")
        else:
            print(f"WARNING: brak markdown.md dla offer_id={offer_id}: {markdown}")
    (TEST_DIR / "TASK.md").write_text("""# Test AI-X przez Codexa

To jest test jakości promptów dla przyszłego API workflow. Docelowy workflow API pozostaje oparty o OpenAI API.

1. Analizuj tylko pola oznaczone `X` w `benchmark_x_sample.csv`.
2. Używaj tylko markdownów z `offer_pages/`.
3. Nie używaj wiedzy ogólnej o modelu i nie zgaduj.
4. Jeśli brak potwierdzenia, zostaw `X`.
5. Nie traktuj rekomendowanych ani sponsorowanych produktów jako danych analizowanej aukcji.
6. Każda uzupełniona wartość musi mieć evidence maksymalnie 300 znaków.

Zapisz wynik jako `codex_ai_x_filled.csv` oraz `codex_ai_x_sources.csv` w tym katalogu.
Po zakończeniu uruchom `python3 scripts/merge_codex_ai_x_test_results.py`.
""", encoding="utf-8")
    schema = {"offer_id": "...", "fields": {"Nazwa pola": {"value": "X", "status": "still_x", "confidence": "high", "evidence": ""}}}
    (TEST_DIR / "expected_output_schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"codex_sample_rows={len(samples)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
