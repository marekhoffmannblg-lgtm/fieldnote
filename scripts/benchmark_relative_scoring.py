"""Deterministic, offline stroller attribute normalization and relative scoring."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "config/categories/strollers.v1.yaml"
MISSING = {"", "-", "—", "n/a", "na", "unknown", "not_applicable", "nie dotyczy", "brak"}


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    # The checked-in YAML uses JSON syntax intentionally: it is valid YAML and
    # keeps the offline gate independent of optional parser packages.
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or len(value.get("attributes", [])) != 21:
        raise ValueError("Schema strollerów musi zawierać dokładnie 21 pól.")
    seen_aliases: dict[str, str] = {}
    for definition in value.get("attributes", []):
        canonical = str(definition.get("key", ""))
        for alias in [canonical, *(definition.get("aliases", []) if isinstance(definition.get("aliases"), list) else [])]:
            normalized = _normalize_key(alias)
            if not normalized:
                continue
            previous = seen_aliases.get(normalized)
            if previous and previous != canonical:
                raise ValueError(f"Kolizja aliasu atrybutu: {alias}")
            seen_aliases[normalized] = canonical
    return value


def _raw(value: Any) -> str:
    return str(value.get("value", "") if isinstance(value, Mapping) else value or "").strip()


def _normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("ł", "l")
    return re.sub(r"[^a-z0-9]+", "", text)


def _conversion_factor(definition: Mapping[str, Any], source_unit: str, target_unit: str) -> float | None:
    source = _normalize_key(source_unit)
    target = _normalize_key(target_unit)
    if not source or not target or source == target:
        return 1.0
    for conversion in definition.get("conversions", []) if isinstance(definition.get("conversions"), list) else []:
        if not isinstance(conversion, Mapping):
            continue
        if _normalize_key(conversion.get("from")) == source and _normalize_key(conversion.get("to")) == target:
            try:
                return float(conversion.get("factor", 1))
            except (TypeError, ValueError):
                return None
    # Keep the historic, explicit conversions as a compatibility fallback for
    # schemas written before conversion metadata was versioned.
    legacy = {("g", "kg"): 0.001, ("mm", "cm"): 0.1}
    return legacy.get((source, target))


def normalize_attribute(value: Any, *, target_unit: str = "", value_type: str = "text", definition: Mapping[str, Any] | None = None) -> Any:
    raw = _raw(value)
    if raw.casefold() in MISSING:
        return None
    if value_type == "boolean":
        folded = raw.casefold()
        if folded in {"yes", "tak", "true", "1", "y"}: return True
        if folded in {"no", "nie", "false", "0", "n"}: return False
        # Source descriptions such as "front and rear" are positive
        # evidence for suspension, while explicit absence remains negative.
        if definition and str(definition.get("key", "")) == "suspension":
            if any(token in folded for token in ("brak", "bez amortyz", "no suspension", "none")):
                return False
            if folded and folded not in MISSING:
                return True
        return None
    if value_type == "number":
        match = re.search(r"-?\d+(?:[.,]\d+)?", raw.replace("\u00a0", " "))
        if not match: return None
        number = float(match.group(0).replace(",", "."))
        source_unit = str(value.get("unit", "") if isinstance(value, Mapping) else "")
        factor = _conversion_factor(definition or {}, source_unit, target_unit)
        if factor is None:
            return None
        number *= factor
        return number
    return raw


def attributes_map(product: Mapping[str, Any], schema: Mapping[str, Any] | None = None) -> dict[str, Any]:
    attrs = product.get("attributes", product.get("specifications", {}))
    values: dict[str, Any] = {}
    if isinstance(attrs, Mapping):
        values.update({str(key): value for key, value in attrs.items()})
    else:
        values.update({str(item.get("key")): item for item in attrs if isinstance(item, Mapping) and item.get("key")})
    if schema is None:
        return values
    aliases: dict[str, str] = {}
    for definition in schema.get("attributes", []):
        canonical = str(definition.get("key", ""))
        for alias in [canonical, *(definition.get("aliases", []) if isinstance(definition.get("aliases"), list) else [])]:
            normalized = _normalize_key(alias)
            if normalized:
                previous = aliases.get(normalized)
                if previous and previous != canonical:
                    raise ValueError(f"Kolizja aliasu atrybutu: {alias}")
                aliases[normalized] = canonical
    normalized_values: dict[str, Any] = {}
    for key, value in values.items():
        canonical = aliases.get(_normalize_key(key), key)
        # Canonical keys win deterministicly over aliases when both are sent.
        if canonical not in normalized_values or _normalize_key(key) == _normalize_key(canonical):
            normalized_values[canonical] = value
    return normalized_values


def _normalized(product: Mapping[str, Any], definition: Mapping[str, Any]) -> Any:
    schema = {"attributes": [definition]}
    value = attributes_map(product, schema).get(str(definition["key"]))
    return normalize_attribute(value, target_unit=str(definition.get("unit", "")), value_type=str(definition.get("type", "text")), definition=definition)


def score_products(products: list[Mapping[str, Any]], *, group_key: str, profile: str = "urban", schema: Mapping[str, Any] | None = None) -> dict[str, Any]:
    schema = schema or load_schema()
    definitions = [item for item in schema["attributes"] if item.get("role") == "scored"]
    group = [p for p in products if str(p.get("benchmark_group", p.get("benchmark_group_key", ""))).strip() == group_key]
    if not group: return {"status":"insufficient_data", "reason":"no_products_in_group", "group_key":group_key, "participants":[]}
    rows = [{"product": p, "values": {d["key"]: _normalized(p, d) for d in definitions}} for p in group]
    scores: dict[str, float] = {str(row["product"].get("product_id", row["product"].get("model", ""))): 0.0 for row in rows}
    weights: dict[str, float] = {}
    contributions: dict[str, dict[str, float]] = {key: {} for key in scores}
    for definition in definitions:
        key, direction = str(definition["key"]), str(definition.get("direction", "higher"))
        present = [(row, row["values"][key]) for row in rows if row["values"][key] is not None]
        if not present: continue
        weight = float(definition.get("weights", {}).get(profile, 1.0))
        if direction == "binary":
            normalized = {id(row["product"]): (1.0 if value is True else 0.0) for row, value in present}
        elif all(isinstance(value, (int, float)) for _, value in present):
            values = [float(value) for _, value in present]; low, high = min(values), max(values)
            normalized = {id(row["product"]): (1.0 if high == low else ((float(value)-low)/(high-low) if direction == "higher" else (high-float(value))/(high-low))) for row, value in present}
        else:
            normalized = {id(row["product"]): 1.0 for row, _ in present}
        weights[key] = weight
        for row, _ in present:
            product_id = str(row["product"].get("product_id", row["product"].get("model", "")))
            contribution = normalized[id(row["product"])] * weight
            scores[product_id] += contribution
            contributions[product_id][key] = round(contribution, 6)
    results = []
    for row in rows:
        product_id = str(row["product"].get("product_id", row["product"].get("model", "")))
        present = sum(value is not None for value in row["values"].values())
        product_weight = sum(weights.get(key, 0.0) for key, value in row["values"].items() if value is not None)
        utility_score = None if product_weight <= 0 else round(scores[product_id] / product_weight * 100, 4)
        results.append({"product_id": product_id, "score": utility_score, "completeness": round(present / len(definitions), 4), "field_contributions": contributions[product_id]})
    results.sort(key=lambda item: (item["score"] is None, -(item["score"] or 0.0), item["product_id"]))
    for position, result in enumerate(results, 1): result["position"] = position
    return {"status":"ok", "group_key":group_key, "profile":profile, "participants":results, "participant_count":len(results), "scored_fields":len(definitions)}


def score_product_group(products: list[Mapping[str, Any]], group_key: str, profile: str = "urban") -> dict[str, Any]:
    return score_products(products, group_key=group_key, profile=profile)
