"""Deterministic, offline stroller attribute normalization and relative scoring."""
from __future__ import annotations

import json
import re
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
    return value


def _raw(value: Any) -> str:
    return str(value.get("value", "") if isinstance(value, Mapping) else value or "").strip()


def normalize_attribute(value: Any, *, target_unit: str = "", value_type: str = "text") -> Any:
    raw = _raw(value)
    if raw.casefold() in MISSING:
        return None
    if value_type == "boolean":
        folded = raw.casefold()
        if folded in {"yes", "tak", "true", "1", "y"}: return True
        if folded in {"no", "nie", "false", "0", "n"}: return False
        return None
    if value_type == "number":
        match = re.search(r"-?\d+(?:[.,]\d+)?", raw.replace("\u00a0", " "))
        if not match: return None
        number = float(match.group(0).replace(",", "."))
        source_unit = str(value.get("unit", "") if isinstance(value, Mapping) else "").casefold()
        if target_unit == "kg" and source_unit == "g": number /= 1000
        if target_unit == "cm" and source_unit == "mm": number /= 10
        return number
    return raw


def attributes_map(product: Mapping[str, Any]) -> dict[str, Any]:
    attrs = product.get("attributes", product.get("specifications", {}))
    if isinstance(attrs, Mapping): return dict(attrs)
    return {str(item.get("key")): item for item in attrs if isinstance(item, Mapping) and item.get("key")}


def _normalized(product: Mapping[str, Any], definition: Mapping[str, Any]) -> Any:
    value = attributes_map(product).get(str(definition["key"]))
    return normalize_attribute(value, target_unit=str(definition.get("unit", "")), value_type=str(definition.get("type", "text")))


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
    total_weight = sum(weights.values()) or 1.0
    results = []
    for row in rows:
        product_id = str(row["product"].get("product_id", row["product"].get("model", "")))
        present = sum(value is not None for value in row["values"].values())
        results.append({"product_id": product_id, "score": round(scores[product_id] / total_weight * 100, 4), "completeness": round(present / len(definitions), 4), "field_contributions": contributions[product_id]})
    results.sort(key=lambda item: (-item["score"], item["product_id"]))
    for position, result in enumerate(results, 1): result["position"] = position
    return {"status":"ok", "group_key":group_key, "profile":profile, "participants":results, "participant_count":len(results), "scored_fields":len(definitions)}


def score_product_group(products: list[Mapping[str, Any]], group_key: str, profile: str = "urban") -> dict[str, Any]:
    return score_products(products, group_key=group_key, profile=profile)
