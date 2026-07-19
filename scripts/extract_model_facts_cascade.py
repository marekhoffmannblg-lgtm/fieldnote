from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from pathlib import Path

from p0_runtime import atomic_write_json
from quality_gate import apply_quality_gate, load_registry

ROOT = Path(__file__).resolve().parent.parent
GROUPS = ROOT / "output" / "model_groups"
FIELDS = ("Marka", "Model", "Status", "Rama", "Koła", "Udźwig", "Regulacja oparcia", "Auto-folding", "Składanie jedną ręką", "Waga", "Wymiary po złożeniu", "Siedzisko", "Amortyzacja", "Koła 360°", "Hamulec", "Budka XXL", "Filtr UPF50+", "Wodoodporna budka", "Regulacja rączki", "Wymiary oparcia / miejsce do spania", "Akcesoria")
NEGATIVE_EVIDENCE = ("brak informacji", "nie podano", "brak danych", "nie określono", "nie znaleziono", "brak wzmianki", "źródło nie podaje")


def normalize_evidence_items(value, current_value="") -> list[dict]:
    keys = ("source_id", "marketplace", "external_offer_id", "source_url", "value", "evidence")
    if value is None or value == "":
        return []
    values = value if isinstance(value, list) else [value]
    normalized = []
    for item in values:
        if item is None or item == "":
            continue
        if isinstance(item, dict):
            normalized.append({key: str(item.get(key, "") or "") for key in keys})
        elif isinstance(item, str):
            normalized.append({"source_id": "", "marketplace": "", "external_offer_id": "", "source_url": "", "value": current_value, "evidence": item})
    return normalized


def validate_field_result(field_name: str, result: dict) -> dict:
    """Reject unsupported AI claims before they can affect model_state."""
    if not isinstance(result, dict):
        return {"value": "X", "status": "open", "confidence": "low", "evidence": ""}
    value = str(result.get("value", "X") or "X").strip()
    evidence = str(result.get("evidence", "") or "").strip()[:300]
    status = str(result.get("status", "unclear"))
    confidence = str(result.get("confidence", "low"))
    invalid = not evidence and value != "X"
    lower = evidence.lower()
    if any(phrase in lower for phrase in NEGATIVE_EVIDENCE): invalid = True
    if field_name == "Auto-folding" and value != "X" and not re.search(r"automatycz|samoczynn|auto\s*-?fold|autofolding", lower): invalid = True
    if field_name == "Koła 360°" and value != "X" and not re.search(r"360\s*°|obrotowe\s+360|skrętne\s+koła\s+przednie", lower): invalid = True
    if field_name == "Budka XXL" and value != "X" and "xxl" not in lower: invalid = True
    if field_name == "Regulacja rączki" and value != "X" and not re.search(r"regulowan[aey]\s+(?:rączk|wysokość)|regulacja\s+wysokości|teleskopow[aey]\s+rączk", lower): invalid = True
    if field_name == "Wymiary oparcia / miejsce do spania" and value != "X" and not re.search(r"\d+(?:[,.]\d+)?\s*[×x]\s*\d+(?:[,.]\d+)?\s*(?:cm|mm)", lower): invalid = True
    if field_name == "Status" and value != "X": invalid = True
    if field_name == "Akcesoria":
        forbidden = {"tak", "nie", "posiada", "jest", "w zestawie", "akcesoria w zestawie"}
        prefix = re.search(r"(?:w zestawie|zestaw zawiera|akcesoria|w komplecie)\s*:\s*(.+)$", evidence, re.IGNORECASE)
        if prefix:
            extracted = re.sub(r"\s+", " ", prefix.group(1)).strip(" .;,-")
            if extracted and extracted.lower() not in forbidden:
                value = extracted
                status = "confirmed"
                confidence = "high"
        if value.lower() in forbidden or value.lower().rstrip(":") in forbidden:
            invalid = True
        if value != "X" and (len(value.split()) < 2 or value.lower() in forbidden): invalid = True
    if invalid:
        return {"value": "X", "status": "open", "confidence": "low", "evidence": ""}
    if value.lower() in {"tak", "jest", "posiada"} and field_name not in {"Auto-folding", "Składanie jedną ręką"}:
        return {"value": "X", "status": "open", "confidence": "low", "evidence": ""}
    return {"value": value, "status": status, "confidence": confidence, "evidence": evidence}


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def new_state(group: dict) -> dict:
    sources = group.get("sources", group.get("offers", []))
    return {"group_key": group["group_key"], "brand": group["brand"], "model": group["model"], "processed_source_ids": [], "remaining_source_ids": [item.get("source_id", f"{item.get('marketplace','allegro')}:{item.get('offer_id', item.get('external_offer_id',''))}") for item in sources], "marketplaces_used": [], "fields": {field: {"value": "X", "status": "open", "confidence": "low", "evidence": [], "locked": False} for field in FIELDS}, "bootstrap_sources_used": [], "bootstrap_fields_imported": 0, "warnings": []}


def bootstrap_state(state: dict, group: dict) -> None:
    for source in group.get("sources", group.get("offers", [])):
        path = source.get("product_facts_ai_path", "")
        if not path:
            continue
        facts = read_json(ROOT / path)
        source_id = source.get("source_id", f"{source.get('marketplace','allegro')}:{source.get('external_offer_id', source.get('offer_id',''))}")
        for field, item in facts.get("fields", {}).items():
            if field not in state["fields"] or not isinstance(item, dict):
                continue
            value = str(item.get("value", "X") or "X"); evidence = str(item.get("evidence", "") or "")[:300]
            if value == "X" or item.get("status") != "confirmed" or not evidence or any(marker in (value + evidence).lower() for marker in ("https://", "events/clicks", "![", "sponsorowane")):
                continue
            current = state["fields"][field]
            entry = {"source_id": source_id, "marketplace": source.get("marketplace", "allegro"), "external_offer_id": source.get("external_offer_id", source.get("offer_id", "")), "source_url": source.get("source_url", ""), "value": value, "evidence": evidence}
            if current["value"] not in ("X", value):
                current["status"] = "conflicting"; current["locked"] = False; current.setdefault("evidence", []).append(entry); continue
            current["value"] = value; current["status"] = "confirmed"; current["confidence"] = item.get("confidence", "low"); current.setdefault("evidence", []).append(entry)
            if current["confidence"] == "high": current["locked"] = True
            state["bootstrap_fields_imported"] = state.get("bootstrap_fields_imported", 0) + 1
        if source_id not in state.setdefault("bootstrap_sources_used", []): state["bootstrap_sources_used"].append(source_id)


def make_prompt(group: dict, offer: dict, target: list[str]) -> str:
    source = read_json(ROOT / offer["offer_sections_path"])
    sections = source.get("sections", {})
    data = {key: sections.get(key, "") for key in ("parameters", "description", "features", "technical_details", "accessories")}
    return f"""Kaskadowa ekstrakcja benchmarku dla marki {group['brand']}, modelu {group['model']}.
marketplace: {offer.get('marketplace','allegro')}
source_id: {offer.get('source_id', '')}
external_offer_id: {offer.get('external_offer_id', offer.get('offer_id',''))}
source_url: {offer['source_url']}
target_fields: {json.dumps(target, ensure_ascii=False)}
Pola już potwierdzone zostały pominięte celowo. Nie zwracaj pól spoza target_fields i nie próbuj ich ponownie analizować.
Nie zgaduj. Każda wartość inna niż X wymaga literalnego evidence, maksymalnie 300 znaków.

Źródło aukcji:
{json.dumps(data, ensure_ascii=False, indent=2)[:16000]}

Zwróć wyłącznie JSON patcha: {{"offer_id":"...","fields":{{"pole":{{"value":"wartość albo X","status":"confirmed|not_found|unclear|conflicting","confidence":"high|medium|low","evidence":"..."}}}},"warnings":[]}}
"""


def call_api(prompt: str, key: str, model: str) -> dict:
    body = {"model": model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": prompt}]}
    request = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode())
    return json.loads(result["choices"][0]["message"]["content"])


def merge(state: dict, patch: dict, source: dict) -> None:
    source_id = source.get("source_id", f"{source.get('marketplace','allegro')}:{source.get('offer_id', source.get('external_offer_id',''))}")
    for field, item in patch.get("fields", {}).items():
        if field not in state["fields"] or not isinstance(item, dict):
            continue
        current = state["fields"][field]
        if current.get("locked"):
            continue
        item = validate_field_result(field, item)
        value = item["value"]
        evidence = item["evidence"]
        if value != "X" and not evidence:
            continue
        if value == "X":
            current["status"] = "open"
            continue
        evidence_item = {"source_id": source_id, "marketplace": source.get("marketplace", "allegro"), "external_offer_id": source.get("external_offer_id", source.get("offer_id", "")), "source_url": source.get("source_url", ""), "value": value, "evidence": evidence}
        if current.get("value") not in ("X", value) and current.get("status") in {"confirmed", "conflicting"}:
            current["status"] = "conflicting"
            current.setdefault("evidence", []).append(evidence_item)
            continue
        current.update({"value": value, "status": item.get("status", "unclear"), "confidence": item.get("confidence", "low")})
        current.setdefault("evidence", []).append(evidence_item)
        if current["status"] == "confirmed" and current["confidence"] == "high":
            current["locked"] = True


def revalidate_states(group_key: str | None = None) -> int:
    """Revalidate persisted evidence locally without prompts or API calls."""
    updated = 0
    matched = False
    registry = load_registry()
    for state_path in GROUPS.glob("*/model_state.json"):
        group = read_json(state_path.parent / "group.json")
        if group_key and group.get("group_key") != group_key:
            continue
        matched = True
        state = read_json(state_path)
        state, _report = apply_quality_gate(state, group, registry)
        atomic_write_json(state_path, state)
        updated += 1
    if group_key and not matched:
        available = sorted({read_json(path.parent / "group.json").get("group_key", "") for path in GROUPS.glob("*/model_state.json") if read_json(path.parent / "group.json").get("group_key")})
        print(f"Nie znaleziono group_key: {group_key}")
        print("Dostępne group_key: " + (", ".join(available) if available else "brak"))
        return 1
    print(f"states_revalidated={updated}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-models", type=int, default=0)
    parser.add_argument("--max-offers-per-model", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reset-state", action="store_true")
    parser.add_argument("--rebuild-state-from-existing-ai", action="store_true")
    parser.add_argument("--model", default="gpt-4.1-nano")
    parser.add_argument("--max-input-chars", type=int, default=16000)
    parser.add_argument("--mock-responses-dir")
    parser.add_argument("--revalidate-state-only", action="store_true")
    parser.add_argument("--group-key")
    args = parser.parse_args()
    if args.revalidate_state_only:
        if args.group_key and args.limit_models:
            print("WARNING: --limit-models został zignorowany, ponieważ podano --group-key.")
        return revalidate_states(args.group_key)
    key = os.environ.get("OPENAI_API_KEY", "")
    if not args.dry_run and not args.mock_responses_dir and not key:
        print("Brak OPENAI_API_KEY. Ustaw zmienną środowiskową albo użyj --dry-run.")
        return 1
    directories = sorted(path for path in GROUPS.iterdir() if (path / "group.json").exists()) if GROUPS.exists() else []
    if args.group_key:
        matches = [path for path in directories if read_json(path / "group.json").get("group_key") == args.group_key]
        if not matches:
            available = sorted({read_json(path / "group.json").get("group_key", "") for path in directories if read_json(path / "group.json").get("group_key")})
            print(f"Nie znaleziono group_key: {args.group_key}")
            print("Dostępne group_key: " + (", ".join(available) if available else "brak"))
            return 1
        directories = matches[:1]
        if args.limit_models:
            print("WARNING: --limit-models został zignorowany, ponieważ podano --group-key.")
    elif args.limit_models:
        directories = directories[: args.limit_models]
    prompts_written = 0
    registry = load_registry()
    for directory in directories:
        group = read_json(directory / "group.json")
        state_path = directory / "model_state.json"
        is_new = args.reset_state or not state_path.exists()
        state = new_state(group) if is_new else read_json(state_path)
        if is_new or args.rebuild_state_from_existing_ai:
            if args.rebuild_state_from_existing_ai:
                state = new_state(group)
            bootstrap_state(state, group)
        (directory / "steps").mkdir(exist_ok=True)
        (directory / "prompts").mkdir(exist_ok=True)
        if args.rebuild_state_from_existing_ai:
            for prompt_file in (directory / "prompts").glob("*.txt"):
                prompt_file.unlink()
        sources = group.get("sources", group.get("offers", []))
        for offer in sources[: args.max_offers_per_model]:
            target = [field for field, item in state["fields"].items() if not item.get("locked") and not (item.get("status") == "confirmed" and item.get("confidence") == "high")]
            source_id = offer.get("source_id", f"{offer.get('marketplace','allegro')}:{offer.get('offer_id', offer.get('external_offer_id',''))}")
            if not target or source_id in state.get("processed_source_ids", []):
                continue
            prompt = make_prompt(group, offer, target)
            step = len(state.get("processed_source_ids", [])) + 1
            (directory / "prompts" / f"step_{step:02d}_{source_id.replace(':','_')}.txt").write_text(prompt[: args.max_input_chars + 4000], encoding="utf-8")
            prompts_written += 1
            if args.dry_run:
                continue
            if args.mock_responses_dir:
                patch = read_json(Path(args.mock_responses_dir) / f"{offer.get('external_offer_id', offer.get('offer_id',''))}.json")
            else:
                patch = call_api(prompt, key, args.model)
            merge(state, patch, offer)
            state.setdefault("processed_source_ids", []).append(source_id)
            state["remaining_source_ids"] = [value for value in state.get("remaining_source_ids", []) if value != source_id]
            state.setdefault("marketplaces_used", [])
            if offer.get("marketplace", "allegro") not in state["marketplaces_used"]: state["marketplaces_used"].append(offer.get("marketplace", "allegro"))
            state, _report = apply_quality_gate(state, group, registry)
            atomic_write_json(state_path, state)
        state, _report = apply_quality_gate(state, group, registry)
        atomic_write_json(state_path, state)
    print(f"groups={len(directories)} prompts_written={prompts_written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
