from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "fill_benchmark_x_with_ai.py"
PROMPTS = ROOT_DIR / "output" / "ai_x_prompts"
FILLED = ROOT_DIR / "output" / "benchmark_ai_filled.csv"
SOURCES = ROOT_DIR / "output" / "benchmark_ai_filled_sources.csv"


def main() -> int:
    failures = []
    result = subprocess.run([sys.executable, str(SCRIPT), "--dry-run", "--limit", "3"], cwd=ROOT_DIR, capture_output=True, text=True, check=False)
    if result.returncode != 0: failures.append("dry_run_failed")
    if not SCRIPT.exists() or not PROMPTS.exists(): failures.append("script_or_prompts_missing")
    prompt_texts = [path.read_text(encoding="utf-8") for path in PROMPTS.glob("*.txt")]
    prompt_text = "\n".join(prompt_texts)
    for phrase in ("Nie zgaduj", "Zwróć X", "Używaj tylko treści aukcji", "Nie używaj wiedzy ogólnej"):
        if phrase not in prompt_text: failures.append(f"prompt_missing:{phrase}")
    for phrase in ("Dbamy o Twoją prywatność", "Podobne oferty", "https://a.allegroimg.com"):
        if phrase.lower() in prompt_text.lower(): failures.append(f"noise_in_prompt:{phrase}")
    if any(len(prompt) >= 15000 for prompt in prompt_texts):
        failures.append("prompt_over_default_limit")
    if not any("Analizuj tylko te pola, które mają X:" in prompt for prompt in prompt_texts):
        failures.append("x_fields_missing")
    if FILLED.exists():
        with FILLED.open(encoding="utf-8", newline="") as handle:
            if tuple(csv.DictReader(handle).fieldnames or ()) != tuple(csv.DictReader(open(ROOT_DIR / "output/benchmark_clean.csv", encoding="utf-8", newline="")).fieldnames or ()):
                failures.append("filled_columns")
    if SOURCES.exists():
        with SOURCES.open(encoding="utf-8", newline="") as handle:
            if "status" not in (csv.DictReader(handle).fieldnames or []): failures.append("source_columns")
    missing = os.environ.copy(); missing.pop("OPENAI_API_KEY", None)
    error = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT_DIR, env=missing, capture_output=True, text=True, check=False)
    if error.returncode == 0 or "OPENAI_API_KEY" not in error.stdout + error.stderr: failures.append("missing_key_error")
    if failures:
        print("FAIL"); print("\n".join(sorted(set(failures)))); return 1
    print("Result: OK"); return 0


if __name__ == "__main__": raise SystemExit(main())
