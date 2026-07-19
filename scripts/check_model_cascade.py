from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import extract_model_facts_cascade as cascade


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as temp:
        fixture = Path(temp)
        original_root = cascade.ROOT
        cascade.ROOT = fixture
        try:
            source_rows = [
                {"source_id": "allegro:1001", "external_offer_id": "1001", "marketplace": "allegro", "source_url": "https://example.test/1001", "offer_sections_path": "sources/1001/offer_sections.json"},
                {"source_id": "allegro:1002", "external_offer_id": "1002", "marketplace": "allegro", "source_url": "https://example.test/1002", "offer_sections_path": "sources/1002/offer_sections.json"},
            ]
            for source in source_rows:
                path = fixture / source["offer_sections_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"sections": {"parameters": "Rama: stal", "description": "Testowy opis", "technical_details": "Waga: 6 kg", "features": "Hamulec"}}), encoding="utf-8")
            group = {"group_key": "kinderkraft|test", "brand": "Kinderkraft", "model": "TEST", "sources": source_rows}
            state = cascade.new_state(group)
            prompts = fixture / "prompts"
            prompts.mkdir()

            first_target = [field for field, item in state["fields"].items() if not item["locked"]]
            first_prompt = cascade.make_prompt(group, source_rows[0], first_target)
            first_path = prompts / "step_01_allegro_1001.txt"
            first_path.write_text(first_prompt, encoding="utf-8")
            cascade.merge(state, {"fields": {"Rama": {"value": "stal", "status": "confirmed", "confidence": "high", "evidence": "Rama: stal"}, "Waga": {"value": "6 kg", "status": "confirmed", "confidence": "high", "evidence": "Waga: 6 kg"}}}, source_rows[0])
            state["processed_source_ids"].append(source_rows[0]["source_id"])

            second_target = [field for field, item in state["fields"].items() if not item["locked"] and not (item["status"] == "confirmed" and item["confidence"] == "high")]
            second_prompt = cascade.make_prompt(group, source_rows[1], second_target)
            second_path = prompts / "step_02_allegro_1002.txt"
            second_path.write_text(second_prompt, encoding="utf-8")
            cascade.merge(state, {"fields": {"Hamulec": {"value": "hamulec nożny", "status": "confirmed", "confidence": "medium", "evidence": "Hamulec nożny"}}}, source_rows[1])
            state["processed_source_ids"].append(source_rows[1]["source_id"])

            # Select exactly by source ID, never by glob order or final-state timing.
            selected = next((path for path in prompts.glob("*.txt") if "allegro_1002" in path.name), None)
            if selected != second_path:
                failures.append("second_prompt_selection")
            match = re.search(r"target_fields:\s*(\[[^\n]+\])", second_path.read_text(encoding="utf-8"))
            if not match:
                failures.append("target_fields_missing")
            else:
                target = json.loads(match.group(1))
                if "Rama" in target:
                    failures.append("locked_field_in_second_prompt:Rama")
                if "Waga" in target:
                    failures.append("locked_field_in_second_prompt:Waga")
                if "Hamulec" not in target:
                    failures.append("open_field_missing_from_second_prompt:Hamulec")
            if [first_path.name, second_path.name] != sorted([first_path.name, second_path.name]):
                failures.append("prompt_names_not_deterministic")
            if state["fields"]["Rama"]["value"] != "stal" or state["fields"]["Waga"]["value"] != "6 kg":
                failures.append("locked_values_changed")
        finally:
            cascade.ROOT = original_root
    if failures:
        print("FAIL")
        print("\n".join(sorted(set(failures))))
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
