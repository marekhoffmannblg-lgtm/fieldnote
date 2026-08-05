"""Build internal Lionelo benchmarks from the deterministic scorer."""
from __future__ import annotations
from typing import Any, Mapping
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from benchmark_relative_scoring import score_products


def build_internal_benchmark(products: list[Mapping[str, Any]], group_key: str, profile: str = "urban") -> dict[str, Any]:
    eligible = [p for p in products if str(p.get("brand", "")).strip().casefold() == "lionelo" and str(p.get("benchmark_group", p.get("benchmark_group_key", ""))).strip() == group_key]
    if len(eligible) < 3:
        return {"status":"insufficient_data", "reason":"internal_benchmark_requires_three_lionelo", "group_key":group_key, "participant_count":len(eligible), "participants":[]}
    return {"benchmark_type":"internal", **score_products(eligible, group_key=group_key, profile=profile)}


class InternalBenchmarkService:
    build = staticmethod(build_internal_benchmark)
