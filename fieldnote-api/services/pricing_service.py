"""Price aggregation kept separate from utility benchmark scoring."""
from __future__ import annotations

from statistics import median
from typing import Any, Mapping


def aggregate_prices(observations: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Return median/min/max over one deterministic observation per seller."""
    chosen: dict[str, Mapping[str, Any]] = {}
    for observation in observations:
        try: price = float(observation.get("price"))
        except (TypeError, ValueError): continue
        if price <= 0: continue
        seller = str(observation.get("seller_id") or observation.get("seller") or observation.get("seller_name") or "").strip().casefold()
        if not seller: continue
        previous = chosen.get(seller)
        current_key = (str(observation.get("observed_at", "")), str(observation.get("source_id", "")))
        previous_key = (str(previous.get("observed_at", "")), str(previous.get("source_id", ""))) if previous else ("", "")
        if previous is None or current_key > previous_key: chosen[seller] = {**observation, "price": price}
    values = sorted(float(item["price"]) for item in chosen.values())
    if not values: return {"status":"no_data", "median":None, "min":None, "max":None, "seller_count":0, "observations":[]}
    return {"status":"ok", "median":median(values), "min":values[0], "max":values[-1], "seller_count":len(values), "observations":[{"seller_id":seller, "price":float(item["price"])} for seller, item in sorted(chosen.items())]}


class PricingService:
    aggregate = staticmethod(aggregate_prices)
