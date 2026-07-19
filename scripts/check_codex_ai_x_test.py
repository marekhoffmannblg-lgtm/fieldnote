from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = ROOT / "output" / "codex_ai_x_test"


def main() -> int:
    failures = []
    result = subprocess.run([sys.executable, str(ROOT / "scripts/prepare_codex_ai_x_test.py"), "--limit", "5"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode: failures.append("prepare_failed")
    for path in (TEST_DIR / "TASK.md", TEST_DIR / "benchmark_x_sample.csv", TEST_DIR / "expected_output_schema.json", ROOT / "scripts/merge_codex_ai_x_test_results.py"):
        if not path.exists(): failures.append(f"missing:{path.name}")
    task = (TEST_DIR / "TASK.md").read_text(encoding="utf-8") if (TEST_DIR / "TASK.md").exists() else ""
    for phrase in ("nie zgaduj", "używaj tylko markdownów", "zostaw `X`", "test jakości promptów", "workflow API"):
        if phrase.lower() not in task.lower(): failures.append(f"task_missing:{phrase}")
    pages_dir = TEST_DIR / "offer_pages"
    pages = list(pages_dir.glob("*.md")) if pages_dir.exists() else []
    if not pages: failures.append("markdowns_missing")
    if (TEST_DIR / "benchmark_x_sample.csv").exists():
        with (TEST_DIR / "benchmark_x_sample.csv").open(encoding="utf-8", newline="") as handle:
            sample = list(csv.DictReader(handle))
        if not sample: failures.append("sample_empty")
        if any(not any(value == "X" for key, value in row.items() if key not in {"brand", "category", "detected_model", "offer_id", "normalized_url"}) for row in sample): failures.append("sample_without_X")
        for row in sample:
            offer_id = row.get("offer_id", "")
            if not (pages_dir / f"{offer_id}.md").is_file():
                failures.append(f"markdown_missing:{offer_id}")
    if failures:
        print("FAIL"); print("\n".join(sorted(set(failures)))); return 1
    print("Result: OK"); return 0


if __name__ == "__main__": raise SystemExit(main())
