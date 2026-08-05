import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fieldnote-api"))
from benchmark_relative_scoring import score_products
from services.internal_benchmark_service import build_internal_benchmark
from services.competitive_benchmark_service import build_competitive_benchmark


def product(pid, brand="Lionelo", group="light_stroller", configuration="", weight="5"):
    return {"product_id": pid, "brand": brand, "benchmark_group": group, "configuration": configuration, "attributes":[{"key":"frame_weight","value":weight,"unit":"kg"},{"key":"one_hand_fold","value":"Tak","unit":""}]}


class RelativeScoringTests(unittest.TestCase):
    def test_missing_field_reduces_completeness_without_zeroing_score(self):
        result = score_products([product("a", weight="5"), product("b", weight="" )], group_key="light_stroller")
        rows = {item["product_id"]: item for item in result["participants"]}
        self.assertGreater(rows["b"]["completeness"], 0)
        self.assertGreaterEqual(rows["b"]["score"], 0)
        self.assertLess(rows["b"]["completeness"], rows["a"]["completeness"])

    def test_price_is_not_an_input_to_utility_score(self):
        base = [product("a", weight="5"), product("b", weight="6")]
        with_prices = [{**item, "price": 99999} for item in base]
        self.assertEqual(score_products(base, group_key="light_stroller"), score_products(with_prices, group_key="light_stroller"))

    def test_internal_requires_three_lionelo_and_keeps_group(self):
        result = build_internal_benchmark([product("a"), product("b"), product("c"), product("x", group="stroller_2in1")], "light_stroller")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["participant_count"], 3)

    def test_competitive_filters_configuration_and_group_and_caps_six(self):
        anchor = product("anchor", configuration="2w1")
        candidates = [product(f"c{i}", brand="Other", configuration="2w1") for i in range(8)] + [product("wrong", brand="Other", group="stroller_3in1", configuration="2w1")]
        result = build_competitive_benchmark(anchor, candidates)
        self.assertEqual(result["participant_count"], 6)
        self.assertNotIn("wrong", result["participant_product_ids"])


if __name__ == "__main__": unittest.main()
