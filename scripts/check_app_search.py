from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_search import is_sponsored, load_market_offers, score_offer, parse_query, search_offers


def main() -> int:
    rows = load_market_offers(ROOT_DIR / "output" / "market_offers.csv")
    failures: list[str] = []
    for query in ("Kinderkraft NUBI 2", "Kinderkraft TIK"):
        results = search_offers(rows, query, min_score=45)
        if not results:
            failures.append(f"no_results:{query}")
            continue
        if any(not item.get("normalized_url") for item in results):
            failures.append(f"missing_normalized_url:{query}")
        if any(not isinstance(item.get("match_score"), (int, float)) for item in results):
            failures.append(f"non_numeric_score:{query}")

    query = parse_query("Kinderkraft NUBI 2")
    matching = {"title": "Kinderkraft NUBI 2 wózek spacerowy", "image_alt_texts": "", "nearby_text": "", "normalized_url": "https://allegro.pl/oferta/nubi-2"}
    accessory = {"title": "Kinderkraft NUBI 2 folia", "image_alt_texts": "", "nearby_text": "", "normalized_url": "https://allegro.pl/oferta/nubi-2-folia"}
    if score_offer(accessory, query)[0] >= score_offer(matching, query)[0]:
        failures.append("accessory_not_lower_score")

    nubi_results = search_offers(rows, "Kinderkraft NUBI 2", min_score=0)
    top_titles = [str(item["title"]).lower() for item in nubi_results[:5]]
    if not any("nubi 2" in title for title in top_titles):
        failures.append("nubi_2_not_in_top_results")
    if any("vesto 2" in title or "moov 2" in title for title in top_titles):
        failures.append("wrong_model_in_nubi_2_top_results")

    sponsored_values = [True, "true", "TRUE", False, "false", ""]
    if sum(is_sponsored(value) for value in sponsored_values) != 3:
        failures.append("sponsored_boolean_normalization")

    if failures:
        print("FAIL")
        for failure in failures:
            print(failure)
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
