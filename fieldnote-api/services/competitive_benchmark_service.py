"""Build bounded external benchmarks without crossing segment/configuration."""
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


def build_competitive_benchmark(anchor: Mapping[str, Any], candidates: list[Mapping[str, Any]], profile: str = "urban", max_participants: int = 6) -> dict[str, Any]:
    group = str(anchor.get("benchmark_group", anchor.get("benchmark_group_key", ""))).strip(); configuration = _configuration(anchor)
    compatible = [p for p in candidates if str(p.get("brand", "")).strip().casefold() != "lionelo" and str(p.get("benchmark_group", p.get("benchmark_group_key", ""))).strip() == group and _configuration(p) == configuration]
    compatible = sorted(compatible, key=lambda p: str(p.get("product_id", p.get("model", ""))))[:max_participants]
    if not compatible: return {"status":"insufficient_data", "reason":"no_compatible_participants", "group_key":group, "configuration":configuration, "participant_count":0, "participants":[]}
    result = score_products([anchor, *compatible], group_key=group, profile=profile)
    result.update({"benchmark_type":"competitive", "anchor_product_id":str(anchor.get("product_id", "")), "configuration":configuration, "participant_count":len(compatible), "participant_product_ids":[str(p.get("product_id", "")) for p in compatible]})
    return result


class CompetitiveBenchmarkService:
    build = staticmethod(build_competitive_benchmark)
