"""Build internal Lionelo benchmarks from the deterministic scorer."""
from __future__ import annotations
from typing import Any, Mapping
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from benchmark_relative_scoring import score_products


def _configuration(product: Mapping[str, Any]) -> str:
    raw = str(product.get("configuration", product.get("stroller_configuration", "")) or "").strip().casefold()
    compact = raw.replace(" ", "").replace("-", "")
    return {"2in1": "2w1", "2w1": "2w1", "3in1": "3w1", "3w1": "3w1", "4in1": "4w1", "4w1": "4w1"}.get(compact, raw)


def build_internal_benchmark(products: list[Mapping[str, Any]], group_key: str, profile: str = "urban", configuration: str | None = None) -> dict[str, Any]:
    eligible = [p for p in products if str(p.get("brand", "")).strip().casefold() == "lionelo" and str(p.get("benchmark_group", p.get("benchmark_group_key", ""))).strip() == group_key]
    if eligible and configuration is None:
        # A group can contain multiple configurations in legacy catalog data;
        # choose the deterministic dominant configuration so a mixed group can
        # never leak across the model+configuration benchmark boundary.
        counts: dict[str, int] = {}
        for product in eligible:
            key = _configuration(product); counts[key] = counts.get(key, 0) + 1
        configuration = sorted(counts, key=lambda key: (-counts[key], key))[0]
    target_configuration = _configuration({"configuration": configuration or ""})
    eligible = [p for p in eligible if _configuration(p) == target_configuration]
    if len(eligible) < 3:
        return {"status":"insufficient_data", "reason":"internal_benchmark_requires_three_lionelo", "group_key":group_key, "configuration":target_configuration, "participant_count":len(eligible), "participants":[]}
    return {"benchmark_type":"internal", "configuration":target_configuration, **score_products(eligible, group_key=group_key, profile=profile)}


class InternalBenchmarkService:
    build = staticmethod(build_internal_benchmark)
