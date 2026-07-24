"""Versioned, evidence-led taxonomy for the stroller benchmark.

Classification relies on persisted source titles and local descriptions, not
on a model name alone.  When the available text does not justify a benchmark
class, the product remains saved but is marked ``review_required`` and is
excluded from cross-product comparison.
"""

from __future__ import annotations

from typing import Any

from quality_gate import normalized
from category_registry import same_benchmark_group, validate_category_assignment


TAXONOMY_VERSION = "v1"
CATEGORY = "Wózki dziecięce"
MULTIFUNCTIONAL = "Wózki wielofunkcyjne"
TRAVEL = "Lekkie spacerówki podróżne"
CLASSIC = "Klasyczne spacerówki"
REVIEW = "Wymaga klasyfikacji"

# Product Profile uses taxonomy to constrain identity.  Keeping this mapping
# here prevents narrative generation from owning category rules.
PROFILE_CATEGORY_TYPES: dict[str, dict[str, tuple[str, ...] | str]] = {
    CATEGORY: {
        "product_type": "stroller",
        "allowed_terms": ("wózek", "wozek", "spacerówka", "spacerowka", "stroller", "buggy"),
        "exclusive_terms": ("stolik dziecięcy", "stolik dzieciecy", "krzesełko dziecięce", "krzeselko dzieciece", "transporter dla dzieci", "fotelik samochodowy", "rowerek biegowy", "łóżeczko dziecięce", "lozeczko dzieciece"),
    },
}


def product_profile_identity(category: str, benchmark_category: str, taxonomy_version: str = TAXONOMY_VERSION) -> dict[str, str | tuple[str, ...]]:
    """Return the persisted-category identity rules used by Product Profile."""
    rule = PROFILE_CATEGORY_TYPES.get(str(category), {})
    product_type = str(rule.get("product_type", "unknown"))
    category_id = ":".join(value for value in (taxonomy_version or TAXONOMY_VERSION, normalized(category).replace(" ", "-"), normalized(benchmark_category).replace(" ", "-")) if value)
    return {
        "product_type": product_type,
        "taxonomy_category_id": category_id,
        "allowed_terms": tuple(rule.get("allowed_terms", ())),
        "exclusive_terms": tuple(rule.get("exclusive_terms", ())),
    }


def classify_from_texts(texts: list[str]) -> dict[str, str]:
    corpus = " ".join(normalized(text) for text in texts if text)
    if any(marker in corpus for marker in ("3w1", "3 w 1", "2w1", "2 w 1", "wielofunkcyj", "gondola", "fotelik")):
        return {
            "category": CATEGORY,
            "subcategory": MULTIFUNCTIONAL,
            "benchmark_category": MULTIFUNCTIONAL,
            "taxonomy_version": TAXONOMY_VERSION,
            "taxonomy_status": "classified",
            "taxonomy_reason": "source_text_multifunctional",
        }
    if any(marker in corpus for marker in ("do samolotu", "kabinowy", "bagaz podreczny", "podrozny")):
        return {
            "category": CATEGORY,
            "subcategory": TRAVEL,
            "benchmark_category": TRAVEL,
            "taxonomy_version": TAXONOMY_VERSION,
            "taxonomy_status": "classified",
            "taxonomy_reason": "source_text_travel",
        }
    if "parasolka" in corpus:
        return {
            "category": CATEGORY,
            "subcategory": CLASSIC,
            "benchmark_category": CLASSIC,
            "taxonomy_version": TAXONOMY_VERSION,
            "taxonomy_status": "classified",
            "taxonomy_reason": "source_text_umbrella_stroller",
        }
    if "wozek spacerow" in corpus or "spacerowka" in corpus:
        return {
            "category": CATEGORY,
            "subcategory": CLASSIC,
            "benchmark_category": CLASSIC,
            "taxonomy_version": TAXONOMY_VERSION,
            "taxonomy_status": "classified",
            "taxonomy_reason": "source_title_stroller",
        }
    return {
        "category": CATEGORY,
        "subcategory": REVIEW,
        "benchmark_category": "",
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_status": "review_required",
        "taxonomy_reason": "insufficient_source_text_for_benchmark_class",
    }


def is_benchmark_eligible(record: dict[str, Any]) -> bool:
    if "category_key" in record or "benchmark_group" in record:
        try:
            validate_category_assignment(record.get("category_key"), record.get("benchmark_group"))
            return True
        except ValueError:
            return False
    return (
        str(record.get("taxonomy_status", "")) == "classified"
        and bool(str(record.get("benchmark_category", "")).strip())
        and bool(str(record.get("taxonomy_version", "")).strip())
    )


def same_benchmark_partition(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if any(key in left or key in right for key in ("category_key", "benchmark_group")):
        return same_benchmark_group(left, right)
    return (
        is_benchmark_eligible(left)
        and is_benchmark_eligible(right)
        and str(left.get("benchmark_category", "")) == str(right.get("benchmark_category", ""))
        and str(left.get("taxonomy_version", "")) == str(right.get("taxonomy_version", ""))
    )


__all__ = [
    "CATEGORY", "CLASSIC", "MULTIFUNCTIONAL", "REVIEW", "TAXONOMY_VERSION", "TRAVEL",
    "classify_from_texts", "is_benchmark_eligible", "same_benchmark_partition", "product_profile_identity",
]
