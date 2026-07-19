"""Versioned, evidence-led taxonomy for the stroller benchmark.

Classification relies on persisted source titles and local descriptions, not
on a model name alone.  When the available text does not justify a benchmark
class, the product remains saved but is marked ``review_required`` and is
excluded from cross-product comparison.
"""

from __future__ import annotations

from typing import Any

from quality_gate import normalized


TAXONOMY_VERSION = "v1"
CATEGORY = "Wózki dziecięce"
MULTIFUNCTIONAL = "Wózki wielofunkcyjne"
TRAVEL = "Lekkie spacerówki podróżne"
CLASSIC = "Klasyczne spacerówki"
REVIEW = "Wymaga klasyfikacji"


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
    return (
        str(record.get("taxonomy_status", "")) == "classified"
        and bool(str(record.get("benchmark_category", "")).strip())
        and bool(str(record.get("taxonomy_version", "")).strip())
    )


def same_benchmark_partition(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        is_benchmark_eligible(left)
        and is_benchmark_eligible(right)
        and str(left.get("benchmark_category", "")) == str(right.get("benchmark_category", ""))
        and str(left.get("taxonomy_version", "")) == str(right.get("taxonomy_version", ""))
    )


__all__ = [
    "CATEGORY", "CLASSIC", "MULTIFUNCTIONAL", "REVIEW", "TAXONOMY_VERSION", "TRAVEL",
    "classify_from_texts", "is_benchmark_eligible", "same_benchmark_partition",
]
