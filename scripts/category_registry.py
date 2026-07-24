"""Canonical category and benchmark-group registry for FIELDNOTE."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "data" / "catalog" / "category_registry.json"


class CategoryValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_category_registry() -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Nie można odczytać rejestru kategorii FIELDNOTE.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Rejestr kategorii FIELDNOTE ma nieprawidłowy format.")
    return {str(key): value for key, value in payload.items() if isinstance(value, dict) and isinstance(value.get("benchmark_groups"), dict)}


def categories_for_api() -> list[dict[str, Any]]:
    return [
        {
            "category_key": key,
            "label": str(value.get("label", key)),
            "benchmark_groups": [
                {"benchmark_group": group_key, "label": str(group_label)}
                for group_key, group_label in value["benchmark_groups"].items()
            ],
        }
        for key, value in load_category_registry().items()
    ]


def validate_category_assignment(category_key: object, benchmark_group: object, *, require_complete: bool = True) -> dict[str, str]:
    category_key = str(category_key or "").strip()
    benchmark_group = str(benchmark_group or "").strip()
    registry = load_category_registry()
    if not category_key:
        if require_complete:
            raise CategoryValidationError("CATEGORY_REQUIRED", "Wybierz kategorię produktu.")
        return {"category_key": "", "benchmark_group": "", "category_label": "", "benchmark_group_label": ""}
    category = registry.get(category_key)
    if not category:
        raise CategoryValidationError("NOT_SUPPORTED", f"Kategoria '{category_key}' nie jest jeszcze obsługiwana.")
    groups = category["benchmark_groups"]
    if not benchmark_group:
        if require_complete:
            raise CategoryValidationError("BENCHMARK_GROUP_REQUIRED", "Wybierz grupę benchmarkową.")
        return {"category_key": category_key, "benchmark_group": "", "category_label": str(category.get("label", category_key)), "benchmark_group_label": ""}
    if benchmark_group not in groups:
        raise CategoryValidationError("INVALID_BENCHMARK_GROUP", "Wybrana grupa nie należy do wskazanej kategorii.")
    return {
        "category_key": category_key,
        "benchmark_group": benchmark_group,
        "category_label": str(category.get("label", category_key)),
        "benchmark_group_label": str(groups[benchmark_group]),
    }


def assignment_from_legacy(category: object, benchmark_category: object) -> dict[str, str]:
    """Derive only unambiguous keys from legacy display labels."""
    category_text = str(category or "").casefold()
    benchmark_text = str(benchmark_category or "").casefold()
    if "wózk" not in category_text and "wozk" not in category_text:
        return validate_category_assignment("", "", require_complete=False)
    if "lekk" in benchmark_text or "podróż" in benchmark_text or "podroz" in benchmark_text:
        return validate_category_assignment("stroller", "light_stroller")
    if "klasycz" in benchmark_text or "standard" in benchmark_text:
        return validate_category_assignment("stroller", "standard_stroller")
    return validate_category_assignment("stroller", "", require_complete=False)


def category_status(record: dict[str, Any]) -> str:
    try:
        validate_category_assignment(record.get("category_key"), record.get("benchmark_group"))
        return "classified"
    except CategoryValidationError:
        return "requires_classification"


def supports_product_type(category_key: object, product_type: object) -> bool:
    assignment = validate_category_assignment(category_key, "", require_complete=False)
    # This is a registered adapter, not an application-wide product assumption.
    return assignment["category_key"] == "stroller" and str(product_type or "") == "stroller"


def same_benchmark_group(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        left_value = validate_category_assignment(left.get("category_key"), left.get("benchmark_group"))
        right_value = validate_category_assignment(right.get("category_key"), right.get("benchmark_group"))
    except CategoryValidationError:
        return False
    return left_value["category_key"] == right_value["category_key"] and left_value["benchmark_group"] == right_value["benchmark_group"]
