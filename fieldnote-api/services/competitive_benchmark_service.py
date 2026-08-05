"""Build bounded external benchmarks without crossing segment/configuration."""
from __future__ import annotations
from typing import Any, Mapping
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from benchmark_relative_scoring import score_products


def build_competitive_benchmark(anchor: Mapping[str, Any], candidates: list[Mapping[str, Any]], profile: str = "urban", max_participants: int = 6) -> dict[str, Any]:
    group = str(anchor.get("benchmark_group", anchor.get("benchmark_group_key", ""))).strip(); configuration = str(anchor.get("configuration", anchor.get("stroller_configuration", ""))).strip()
    compatible = [p for p in candidates if str(p.get("brand", "")).strip().casefold() != "lionelo" and str(p.get("benchmark_group", p.get("benchmark_group_key", ""))).strip() == group and str(p.get("configuration", p.get("stroller_configuration", ""))).strip() == configuration]
    compatible = sorted(compatible, key=lambda p: str(p.get("product_id", p.get("model", ""))))[:max_participants]
    if not compatible: return {"status":"insufficient_data", "reason":"no_compatible_participants", "group_key":group, "participant_count":0, "participants":[]}
    result = score_products([anchor, *compatible], group_key=group, profile=profile)
    result.update({"benchmark_type":"competitive", "anchor_product_id":str(anchor.get("product_id", "")), "participant_count":len(compatible), "participant_product_ids":[str(p.get("product_id", "")) for p in compatible]})
    return result


class CompetitiveBenchmarkService:
    build = staticmethod(build_competitive_benchmark)
