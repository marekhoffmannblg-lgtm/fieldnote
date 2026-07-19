from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "output" / "ai_extractor_prompts"


def main() -> int:
    failures = []
    env = os.environ.copy(); env.pop("OPENAI_API_KEY", None)
    result = subprocess.run([sys.executable, str(ROOT / "scripts/extract_product_facts_with_ai.py"), "--dry-run", "--limit", "2", "--force"], cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode != 0 or "prompts_written=" not in result.stdout: failures.append("dry_run_failed")
    prompts = list(PROMPTS.glob("*.txt")) if PROMPTS.exists() else []
    if not prompts: failures.append("prompts_missing")
    if prompts:
        text = prompts[0].read_text(encoding="utf-8")
        for phrase in ("offer_id", "Schema JSON", "Nie zgaduj", "X oznacza brak potwierdzenia", "Nie używaj wiedzy ogólnej", "reviews_summary", "source_quality", "product_images MUSI być listą obiektów", "detected_brand można użyć do pola Marka", "detected_model można użyć do pola Model", "Rama: aluminium", "Jeśli literalny fragment istnieje, pole nie może zostać X", "Mapowanie pól i terminów"):
            if phrase.lower() not in text.lower(): failures.append(f"prompt_missing:{phrase}")
        if text.count('"value": "X"') > 2: failures.append("default_x_schema_regression")
        if text.lower().count("image_candidates") > 1: failures.append("too_many_image_candidate_sections")
        if text.lower().count("s128") > 3: failures.append("too_many_s128_images")
        if "seller-extras-ad" in text.lower() or "seller_info_text" in text.lower(): failures.append("seller_details_leaked")
    no_key = subprocess.run([sys.executable, str(ROOT / "scripts/extract_product_facts_with_ai.py"), "--limit", "1"], cwd=ROOT, env=env, capture_output=True, text=True)
    if no_key.returncode == 0 or "Brak OPENAI_API_KEY" not in (no_key.stdout + no_key.stderr): failures.append("missing_key_error")
    if not (ROOT / "scripts/build_benchmark_ai_validated.py").exists(): failures.append("validator_missing")
    queue_path = ROOT / "output" / "firecrawl_offer_queue.csv"
    with queue_path.open(encoding="utf-8", newline="") as handle:
        fetched = next((row for row in csv.DictReader(handle) if row.get("status") == "fetched"), None)
    if fetched:
        facts_path = ROOT / "input" / "firecrawl_offer_pages" / fetched["offer_id"] / "product_facts_ai.json"
        original = facts_path.read_bytes() if facts_path.exists() else None
        test_facts = {"offer_id": fetched["offer_id"], "source_url": fetched.get("normalized_url", ""), "detected_brand": "Kinderkraft", "detected_model": "TIK", "detected_title": "TIK Kinderkraft", "price": "", "fields": {"Marka": {"value": "X"}, "Model": {"value": "X"}}, "product_images": ["https://example.test/image.jpg"], "reviews_summary": {}, "source_quality": {}, "warnings": []}
        try:
            facts_path.write_text(json.dumps(test_facts), encoding="utf-8")
            build = subprocess.run([sys.executable, str(ROOT / "scripts/build_benchmark_ai_validated.py")], cwd=ROOT, capture_output=True, text=True)
            if build.returncode != 0: failures.append("builder_string_images_failed")
            for output_name in ("benchmark_ai_validated.csv", "benchmark_ai_sources.csv", "benchmark_ai_quality_report.json"):
                if not (ROOT / "output" / output_name).exists(): failures.append(f"missing_builder_output:{output_name}")
            if build.returncode == 0:
                with (ROOT / "output" / "benchmark_ai_validated.csv").open(encoding="utf-8", newline="") as handle:
                    row = next(csv.DictReader(handle), {})
                if row.get("Marka") != "Kinderkraft" or row.get("Model") != "TIK": failures.append("brand_model_fallback_failed")
        finally:
            if original is None: facts_path.unlink(missing_ok=True)
            else: facts_path.write_bytes(original)
    source = (ROOT / "scripts/extract_product_facts_with_ai.py").read_text(encoding="utf-8")
    if 'parser.add_argument("--model", default="gpt-4.1-nano")' not in source: failures.append("default_model_not_gpt_4_1_nano")
    override = subprocess.run([sys.executable, str(ROOT / "scripts/extract_product_facts_with_ai.py"), "--dry-run", "--limit", "1", "--force", "--model", "gpt-4.1-mini"], cwd=ROOT, env=env, capture_output=True, text=True)
    if override.returncode != 0: failures.append("model_override_failed")
    if failures:
        print("FAIL\n" + "\n".join(sorted(set(failures)))); return 1
    print("Result: OK"); return 0


if __name__ == "__main__": raise SystemExit(main())
