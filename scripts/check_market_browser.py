from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_search import browse_market_rows, enrich_market_rows, load_market_offers, market_model_summary


def main() -> int:
    rows = enrich_market_rows(load_market_offers(ROOT_DIR / "output" / "market_offers.csv"))
    summary = market_model_summary(rows)
    models = {str(item["detected_model"]) for item in summary}
    failures: list[str] = []

    if len(models) < 5:
        failures.append("fewer_than_five_detected_models")
    for model in ("NUBI", "TIK", "TRIG"):
        if not any(detected.startswith(model) for detected in models):
            failures.append(f"missing_model:{model}")
    if any(int(item["offers_count"]) <= 0 for item in summary):
        failures.append("model_without_offers")

    nubi_rows = browse_market_rows(rows, model="NUBI 2", hide_accessories=False, show_sponsored=True, min_price=None, max_price=None, sort_by="match_score")
    if not nubi_rows:
        failures.append("nubi_2_has_no_rows")
    if any("vesto" in str(row["title"]).lower() for row in nubi_rows):
        failures.append("vesto_in_nubi_2_group")

    if not any(bool(row["is_accessory"]) and row["detected_model"] == "Accessory / part" for row in rows):
        failures.append("accessories_not_marked")

    if failures:
        print("FAIL")
        for failure in failures:
            print(failure)
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
