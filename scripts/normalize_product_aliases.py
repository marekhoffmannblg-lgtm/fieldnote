"""Deterministic product identity and alias normalisation for Unit 7."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable


CONFIGURATIONS = {"2w1", "3w1", "4w1", "2in1", "3in1", "4in1"}
COLOUR_WORDS = {"black", "white", "grey", "gray", "red", "blue", "green", "beige", "czarny", "czarna", "bialy", "biały", "szary", "czerwony", "niebieski", "zielony", "beżowy"}
NORMALIZED_COLOUR_WORDS = {"black", "white", "grey", "gray", "red", "blue", "green", "beige", "czarny", "czarna", "bialy", "szary", "czerwony", "niebieski", "zielony", "bezowy"}


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).replace("²", "2").replace("³", "3")
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    return re.sub(r"\s+", " ", text).strip()


def slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(value)).strip("-")


def canonical_product_key(brand: str, model: str, configuration: str | None = None) -> str:
    parts = [slug(brand), slug(model)]
    config = fold(configuration)
    if config:
        config = config.replace("in1", "w1")
        parts.append(slug(config))
    return "|".join(part for part in parts if part)


def normalize_alias(value: str, *, brand: str = "", model: str = "", configuration: str | None = None) -> str:
    """Return an alias key while ignoring colour and preserving configuration."""
    text = fold(value)
    for colour in NORMALIZED_COLOUR_WORDS:
        text = re.sub(rf"\b{re.escape(colour)}\b", " ", text)
    text = re.sub(r"\b(?:kolor|colour)\s*[:\-]?\s*[a-z]+\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return canonical_product_key(brand, model, configuration) if brand and model else slug(text)


def _configuration_from_text(value: str) -> str | None:
    match = re.search(r"\b([234])\s*(?:w1|in1)\b", fold(value))
    return f"{match.group(1)}w1" if match else None


def _model_without_variants(value: str) -> str:
    text = fold(value)
    text = re.sub(r"\b[234]\s*(?:w1|in1)\b", " ", text)
    text = re.sub(r"\b(?:kolor|colour)\s*[:\-]?\s*[a-z]+\b", " ", text)
    for colour in NORMALIZED_COLOUR_WORDS:
        text = re.sub(rf"\b{re.escape(colour)}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def alias_record(record: dict[str, Any]) -> dict[str, Any]:
    brand = str(record.get("brand") or "").strip()
    title = str(record.get("title") or "").strip()
    raw_model = str(record.get("model") or title or "").strip()
    if not record.get("model") and brand:
        raw_model = re.sub(rf"^{re.escape(brand)}\b[\s:,-]*", "", raw_model, flags=re.IGNORECASE)
    configuration = str(record.get("configuration") or "").strip() or _configuration_from_text(" ".join((raw_model, title)))
    model = _model_without_variants(raw_model)
    if not model and title:
        model = _model_without_variants(title)
    display_model = str(record.get("model") or model).strip()
    key = canonical_product_key(brand, model, configuration)
    aliases = {str(item).strip() for item in (record.get("aliases") or []) if str(item).strip()}
    if record.get("title"):
        aliases.add(str(record["title"]).strip())
    return {**record, "canonical_key": key, "brand": brand, "model": display_model, "configuration": configuration or "", "aliases": sorted(aliases), "identity_status": "classified" if brand and model and not _placeholder(model) else "excluded"}


def normalize_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for raw in records:
        item = alias_record(raw)
        key = item["canonical_key"]
        if item["identity_status"] == "excluded":
            continue
        current = grouped.get(key)
        if current is None:
            grouped[key] = item
        else:
            grouped[key] = _merge_alias_records(current, item)
    return sorted(grouped.values(), key=lambda item: item["canonical_key"])


def _merge_alias_records(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Merge duplicate identities without making classification order-dependent."""
    candidates = (left, right)
    stable_fields = {key: value for key, value in left.items() if key not in {"aliases", "source_ids", "canonical_key"}}
    base = min(candidates, key=lambda item: json.dumps({key: item.get(key) for key in stable_fields}, ensure_ascii=False, sort_keys=True, default=str))
    merged = dict(base)
    merged["aliases"] = sorted(set(left.get("aliases", [])) | set(right.get("aliases", [])))
    merged["source_ids"] = sorted(set(left.get("source_ids", [])) | set(right.get("source_ids", [])))

    groups = {str(item.get("benchmark_group") or item.get("benchmark_group_key") or "").strip() for item in candidates}
    groups.discard("")
    if len(groups) > 1:
        merged["catalog_status"] = "review_required"
        merged["classification_reason"] = "conflicting_benchmark_groups"
    elif groups and any("catalog_status" in item for item in candidates):
        group = sorted(groups)[0]
        merged["benchmark_group"] = group
        merged["benchmark_group_key"] = group
        merged["catalog_status"] = "classified"
        merged["classification_reason"] = "official_catalog"
    elif any(item.get("catalog_status") == "review_required" for item in candidates):
        merged["catalog_status"] = "review_required"
    return merged


def _placeholder(model: str) -> bool:
    return fold(model) in {"accessory / part", "accessory", "part", "unknown", "test"}


def load_records(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("products", value.get("items", []))
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = normalize_records(load_records(args.input))
    payload = {"schema_version": "1", "items": records, "total": len(records)}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
