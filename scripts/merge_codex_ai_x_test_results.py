from __future__ import annotations

import csv
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CLEAN = ROOT_DIR / "output" / "benchmark_clean.csv"
TEST_DIR = ROOT_DIR / "output" / "codex_ai_x_test"
FILLED = TEST_DIR / "codex_ai_x_filled.csv"
SOURCES = TEST_DIR / "codex_ai_x_sources.csv"
OUT = ROOT_DIR / "output" / "benchmark_codex_ai_test_filled.csv"
OUT_SOURCES = ROOT_DIR / "output" / "benchmark_codex_ai_test_sources.csv"


def read(path: Path) -> list[dict[str, str]]:
    if not path.exists(): return []
    with path.open(encoding="utf-8", newline="") as handle: return list(csv.DictReader(handle))


def main() -> int:
    base = read(CLEAN)
    proposed = {row.get("offer_id", ""): row for row in read(FILLED)}
    evidence = {(row.get("offer_id", ""), row.get("field_name", "")): row for row in read(SOURCES)}
    benchmark_fields = [key for key in base[0] if key not in {"brand", "category", "detected_model", "offer_id", "normalized_url"}] if base else []
    accepted_sources = []
    for row in base:
        candidate = proposed.get(row.get("offer_id", ""), {})
        for field in benchmark_fields:
            if row.get(field) != "X":
                continue
            new_value = candidate.get(field, "X")
            source = evidence.get((row.get("offer_id", ""), field), {})
            if new_value and new_value != "X" and source.get("evidence", "").strip():
                row[field] = new_value
                accepted_sources.append({**source, "status": "filled"})
            elif new_value != "X":
                accepted_sources.append({**source, "new_value": "X", "status": "rejected_no_evidence"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(base[0].keys()) if base else []); writer.writeheader(); writer.writerows(base)
    fields = ("offer_id", "detected_model", "field_name", "old_value", "new_value", "status", "confidence", "evidence", "normalized_url")
    with OUT_SOURCES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(accepted_sources)
    print(f"merged_rows={len(base)} accepted={len(accepted_sources)}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
