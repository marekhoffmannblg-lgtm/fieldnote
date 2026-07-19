"""Deterministic final-field quality gate for FIELDNOTE.

The gate is deliberately offline: it only consumes persisted model states,
group metadata, the source registry and local snapshots.  It never calls an
LLM and never infers a value from general product knowledge.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
FIELDS = (
    "Marka", "Model", "Status", "Rama", "Koła", "Udźwig", "Regulacja oparcia",
    "Auto-folding", "Składanie jedną ręką", "Waga", "Wymiary po złożeniu",
    "Siedzisko", "Amortyzacja", "Koła 360°", "Hamulec", "Budka XXL",
    "Filtr UPF50+", "Wodoodporna budka", "Regulacja rączki",
    "Wymiary oparcia / miejsce do spania", "Akcesoria",
)
NO_INFORMATION = (
    "brak informacji", "nie podano", "brak danych", "nie okreslono",
    "nie znaleziono", "brak wzmianki", "zrodlo nie podaje", "brak bezposredniego",
)
FRAME_MATERIALS = ("aluminium", "alumini", "stal", "steel")
FRAME_COLORS = ("czarn", "taupe", "beige", "bezow", "black", "grey", "gray", "blue", "pink")
OPTIONAL_ACCESSORIES = ("za doplata", "opcjonal", "do kupienia", "sprzedawan", "osobno")


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.replace("ł", "l").replace("Ł", "L").lower()).strip()


def normalize_value(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalized(value)).strip()


def evidence_items(raw: object, current_value: object = "") -> list[dict[str, str]]:
    """Normalize legacy dict/list/string evidence without inventing provenance."""
    values = raw if isinstance(raw, list) else [raw]
    items: list[dict[str, str]] = []
    for value in values:
        if isinstance(value, dict):
            items.append({
                "source_id": str(value.get("source_id", "") or "").strip(),
                "marketplace": str(value.get("marketplace", "") or "").strip(),
                "external_offer_id": str(value.get("external_offer_id", value.get("offer_id", "")) or "").strip(),
                "source_url": str(value.get("source_url", "") or "").strip(),
                "value": str(value.get("value", current_value) or current_value or "").strip(),
                "evidence": str(value.get("evidence", "") or "").strip(),
            })
        elif isinstance(value, str) and value.strip():
            items.append({
                "source_id": "", "marketplace": "", "external_offer_id": "", "source_url": "",
                "value": str(current_value or "").strip(), "evidence": value.strip(),
            })
    return items


def load_registry(path: Path | None = None) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    target = path or ROOT / "output" / "source_registry.jsonl"
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return records
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("source_id"):
            records[str(item["source_id"])] = item
    return records


def source_lookup(group: dict[str, Any], registry: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for source in group.get("sources", []) if isinstance(group.get("sources"), list) else []:
        if not isinstance(source, dict) or not source.get("source_id"):
            continue
        source_id = str(source["source_id"])
        sources[source_id] = {**source, **registry.get(source_id, {})}
    return sources


def source_text(source: dict[str, Any]) -> str:
    candidates = ("content_path", "offer_sections_path", "manufacturer_source_path")
    for key in candidates:
        raw_path = str(source.get(key, "") or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        if path.is_dir():
            path = path / "technical_clean.md"
        try:
            if path.suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                sections = data.get("sections", {}) if isinstance(data, dict) else {}
                return "\n".join(str(value) for value in sections.values() if value)
            return path.read_text(encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            continue
    return ""


def attribute_legacy(item: dict[str, str], sources: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Attach legacy evidence only when its literal text exists in one snapshot."""
    if item.get("source_id"):
        return item
    needle = normalized(item.get("evidence", ""))
    if not needle or len(needle) < 8:
        return item
    for source_id, source in sources.items():
        if needle in normalized(source_text(source)):
            enriched = dict(item)
            enriched["source_id"] = source_id
            enriched["marketplace"] = str(source.get("marketplace", "") or "")
            enriched["external_offer_id"] = str(source.get("external_offer_id", source.get("offer_id", "")) or "")
            enriched["source_url"] = str(source.get("canonical_url", source.get("source_url", "")) or "")
            return enriched
    return item


def contains_any(text: str, values: tuple[str, ...]) -> bool:
    return any(value in text for value in values)


def field_directness(field_name: str, value: str, evidence: str, expected_brand: str, expected_model: str) -> tuple[str, str]:
    """Return (validation_status, reason) for one literal field witness."""
    text = normalized(evidence)
    value_norm = normalize_value(value)
    if not text:
        return "rejected", "brak_evidence"
    if contains_any(text, NO_INFORMATION):
        return "rejected", "evidence_brak_informacji"
    if value_norm in {"", "x", "tak", "nie", "jest", "posiada"} and field_name not in {"Składanie jedną ręką", "Auto-folding", "Koła 360°"}:
        return "rejected", "wartosc_niejednoznaczna"
    if field_name == "Marka":
        return ("valid", "") if expected_brand and normalized(expected_brand) in text else ("rejected", "marka_niepotwierdzona_doslowne")
    if field_name == "Model":
        model_tokens = normalize_value(expected_model).split()
        return ("valid", "") if model_tokens and all(token in text.split() for token in model_tokens) else ("rejected", "model_niepotwierdzony_doslowne")
    if field_name == "Status":
        return "rejected", "brak_jednoznacznej_definicji_statusu"
    if field_name == "Rama":
        if contains_any(text, FRAME_COLORS) and not contains_any(text, FRAME_MATERIALS):
            return "rejected", "wariant_koloru_ramy_nie_jest_materialem"
        return ("valid", "") if contains_any(text, FRAME_MATERIALS) and contains_any(normalized(value), FRAME_MATERIALS) else ("rejected", "brak_materialu_ramy")
    if field_name == "Składanie jedną ręką":
        return ("valid", "") if contains_any(text, ("jedna reka", "jedna reke", "jednym ruchem", "click fold")) else ("rejected", "brak_doslownego_skladania_jedna_reka")
    if field_name == "Auto-folding":
        return ("valid", "") if contains_any(text, ("auto folding", "autofolding", "automatyczne skladanie", "samoczynne skladanie")) else ("rejected", "brak_auto_foldingu")
    if field_name == "Koła 360°":
        return ("valid", "") if contains_any(text, ("360", "obrotowe", "skretne kola przednie")) else ("rejected", "brak_literalnego_360")
    if field_name == "Budka XXL":
        return ("valid", "") if "xxl" in text else ("rejected", "brak_literalnego_xxl")
    if field_name == "Filtr UPF50+":
        return ("valid", "") if contains_any(text, ("upf50", "upf 50", "uv 50")) else ("rejected", "brak_filtra_upf50")
    if field_name == "Wodoodporna budka":
        return ("valid", "") if "budka" in text and contains_any(text, ("wodoodpor", "odporny na deszcz")) else ("rejected", "brak_wodoodpornej_budki")
    if field_name == "Regulacja rączki":
        return ("valid", "") if contains_any(text, ("regulowana raczka", "regulacja raczki", "teleskopowa raczka", "wysokosc raczki")) else ("rejected", "brak_regulacji_raczki")
    if field_name == "Wymiary oparcia / miejsce do spania":
        return ("valid", "") if re.search(r"\d+\s*(?:x|×)\s*\d+\s*cm|\d+\s*cm", text) and contains_any(text, ("oparcie", "spania", "lezenia")) else ("rejected", "brak_wymiaru_oparcia_lub_spania")
    if field_name == "Akcesoria":
        if contains_any(text, OPTIONAL_ACCESSORIES):
            return "rejected", "akcesorium_opcjonalne_nie_jest_elementem_zestawu"
        concrete = ("torba", "folia", "moskitiera", "adapter", "pokrowiec", "pasek", "uchwyt", "tacka", "pałąk", "palak")
        return ("valid", "") if contains_any(text, ("w zestawie", "zestaw zawiera", "w komplecie", "akcesoria")) and contains_any(text, concrete) else ("rejected", "brak_konkretnej_listy_akcesoriow")
    if field_name == "Waga":
        return ("valid", "") if "kg" in text and contains_any(text, ("waga", "wazy")) else ("rejected", "brak_wagi_w_kg")
    if field_name == "Udźwig":
        return ("valid", "") if "kg" in text and contains_any(text, ("obciazenie", "udzwig", "do 22", "do 25", "maksymalne")) else ("rejected", "brak_udzwigu")
    if field_name == "Wymiary po złożeniu":
        return ("valid", "") if "cm" in text and contains_any(text, ("po zlozeniu", "zlozony", "wymiary")) else ("rejected", "brak_wymiarow_po_zlozeniu")
    if field_name == "Regulacja oparcia":
        return ("valid", "") if contains_any(text, ("oparcie", "pozycja lezaca", "regulacja oparcia")) else ("rejected", "brak_regulacji_oparcia")
    if field_name == "Siedzisko":
        return ("valid", "") if contains_any(text, ("siedzisko", "podnozek", "oparcie")) else ("rejected", "brak_cechy_siedziska")
    if field_name == "Amortyzacja":
        return ("valid", "") if contains_any(text, ("amortyz", "amortyzowane")) else ("rejected", "brak_amortyzacji")
    if field_name == "Koła":
        return ("valid", "") if contains_any(text, ("kola", "koła", "eva", "piank", "pompowan", "gumow")) else ("rejected", "brak_parametru_kol")
    if field_name == "Hamulec":
        return ("valid", "") if "hamulec" in text else ("rejected", "brak_hamulca")
    # A conservative fallback for fields without a dedicated rule.
    return ("valid", "") if value_norm and value_norm in normalize_value(evidence) else ("weak", "evidence_posrednie")


def gate_field(field_name: str, field: dict[str, Any], expected_brand: str, expected_model: str, sources: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    current_value = str(field.get("value", "X") or "X").strip()
    raw_items = evidence_items(field.get("evidence"), current_value)
    assessed: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    accepted: list[dict[str, str]] = []
    legacy_seen = False
    for raw_item in raw_items:
        item = attribute_legacy(raw_item, sources)
        source_id = item.get("source_id", "")
        source = sources.get(source_id, {})
        if not source_id:
            legacy_seen = True
            item.update({"validation_status": "unattributed_legacy", "evidence_status": "unattributed", "content_family_id": ""})
            assessed.append(item)
            continue
        if not source:
            item.update({"validation_status": "rejected", "evidence_status": "missing_source", "content_family_id": ""})
            rejected.append({"field_name": field_name, "value": current_value, "source_id": source_id, "reason": "source_id_poza_grupa"})
            assessed.append(item)
            continue
        source_model = normalized(source.get("normalized_model", source.get("model", "")))
        if source_model and source_model != normalized(expected_model):
            item.update({"validation_status": "rejected", "evidence_status": "other_model", "content_family_id": str(source.get("content_family_id", "") or "")})
            rejected.append({"field_name": field_name, "value": current_value, "source_id": source_id, "reason": "zrodlo_innego_modelu"})
            assessed.append(item)
            continue
        status, reason = field_directness(field_name, item.get("value") or current_value, item.get("evidence", ""), expected_brand, expected_model)
        item.update({
            "validation_status": status,
            "evidence_status": "direct" if status == "valid" else "partial" if status == "weak" else "rejected",
            "content_family_id": str(source.get("content_family_id", "") or source_id),
        })
        assessed.append(item)
        if status in {"valid", "weak"}:
            accepted.append(item)
        else:
            rejected.append({"field_name": field_name, "value": current_value, "source_id": source_id, "reason": reason})

    quality_base = {
        "field_name": field_name,
        "normalized_value": normalize_value(current_value),
        "source_id": "",
        "evidence_excerpt": "",
        "evidence_status": "missing",
        "confidence": "low",
        "validation_status": "rejected",
        "content_family_id": "",
    }
    updated = dict(field)
    if current_value == "X" and not raw_items:
        updated.update({"value": "X", "status": "open", "confidence": "low", "locked": False, "validation_status": "rejected", "quality": quality_base, "evidence_quality": []})
        return updated, rejected
    if not accepted:
        status = "unattributed_legacy" if legacy_seen and not rejected else "rejected"
        quality_base["validation_status"] = status
        quality_base["evidence_status"] = "unattributed" if status == "unattributed_legacy" else "rejected"
        updated.update({"value": "X", "status": "open", "confidence": "low", "locked": False, "validation_status": status, "quality": quality_base, "evidence_quality": assessed})
        return updated, rejected

    values_by_family: dict[str, set[str]] = {}
    for item in accepted:
        family = str(item.get("content_family_id") or item.get("source_id"))
        values_by_family.setdefault(family, set()).add(normalize_value(item.get("value") or current_value))
    independent_values = {value for values in values_by_family.values() for value in values if value}
    first = accepted[0]
    quality_base.update({
        "normalized_value": normalize_value(first.get("value") or current_value),
        "source_id": first.get("source_id", ""),
        "evidence_excerpt": str(first.get("evidence", ""))[:300],
        "evidence_status": first.get("evidence_status", "direct"),
        "confidence": "high" if first.get("validation_status") == "valid" else "medium",
        "content_family_id": first.get("content_family_id", ""),
    })
    if len(independent_values) > 1 and len(values_by_family) > 1:
        quality_base["validation_status"] = "conflicting"
        updated.update({"value": "X", "status": "conflicting", "confidence": "low", "locked": False, "validation_status": "conflicting", "quality": quality_base, "evidence_quality": assessed})
        return updated, rejected
    validation_status = "valid" if any(item.get("validation_status") == "valid" for item in accepted) else "weak"
    final_value = str(first.get("value") or current_value)
    quality_base["validation_status"] = validation_status
    updated.update({
        "value": final_value,
        "status": "confirmed",
        "confidence": "high" if validation_status == "valid" else "medium",
        "locked": validation_status == "valid",
        "validation_status": validation_status,
        "quality": quality_base,
        "evidence": assessed,
        "evidence_quality": assessed,
    })
    return updated, rejected


def apply_quality_gate(state: dict[str, Any], group: dict[str, Any], registry: dict[str, dict[str, Any]] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate fields in-place and return a serializable rejection report."""
    registry = registry if registry is not None else load_registry()
    sources = source_lookup(group, registry)
    fields = state.get("fields", {}) if isinstance(state.get("fields"), dict) else {}
    rejections: list[dict[str, str]] = []
    counts = {"valid": 0, "weak": 0, "conflicting": 0, "rejected": 0, "unattributed_legacy": 0}
    for field_name in FIELDS:
        raw_field = fields.get(field_name, {})
        field = raw_field if isinstance(raw_field, dict) else {"value": "X", "evidence": []}
        updated, field_rejections = gate_field(field_name, field, str(state.get("brand", group.get("brand", ""))), str(state.get("model", group.get("model", ""))), sources)
        fields[field_name] = updated
        validation = str(updated.get("validation_status", "rejected"))
        counts[validation if validation in counts else "rejected"] += 1
        rejections.extend(field_rejections)
    # Empty X fields are missing evidence, not rejected factual claims.  Keep
    # their field-level validation marker conservative, but report only actual
    # invalid assertions as rejections.
    rejected_claim_fields = {item["field_name"] for item in rejections}
    counts["rejected"] = len(rejected_claim_fields)
    state["fields"] = fields
    state["quality_gate"] = {"version": "p1-quality-gate-v1", "validated_at": None, **counts}
    report = {
        "product_slug": "",
        "group_key": str(state.get("group_key", group.get("group_key", ""))),
        "fields_before": len(FIELDS),
        "fields_valid": counts["valid"],
        "fields_weak": counts["weak"],
        "fields_conflicting": counts["conflicting"],
        "fields_rejected": counts["rejected"],
        "fields_unattributed_legacy": counts["unattributed_legacy"],
        "fields_missing": sum(
            1 for item in fields.values()
            if isinstance(item, dict) and str(item.get("value", "X")) == "X" and not item.get("evidence_quality")
        ),
        "rejections": rejections,
    }
    return state, report


def coverage_points(field: dict[str, Any]) -> float:
    validation = str(field.get("validation_status", ""))
    if validation == "valid" and str(field.get("value", "X")) != "X":
        return 1.0
    if validation == "weak" and str(field.get("value", "X")) != "X":
        return 0.5
    return 0.0


__all__ = ["FIELDS", "apply_quality_gate", "coverage_points", "evidence_items", "load_registry", "normalize_value", "normalized"]
