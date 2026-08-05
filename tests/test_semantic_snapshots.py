import unittest
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))
sys.path.insert(0, str(ROOT / "tests"))
from services.pricing_service import aggregate_prices
from services.internal_benchmark_service import build_internal_benchmark
from test_relative_benchmark_scoring import product


class SemanticSnapshotTests(unittest.TestCase):
    def test_same_inputs_are_deterministic(self):
        products = [product("a"), product("b"), product("c")]
        first = build_internal_benchmark(products, "light_stroller")
        second = build_internal_benchmark(products, "light_stroller")
        self.assertEqual(first, second)

    def test_price_summary_is_separate_from_score(self):
        benchmark = build_internal_benchmark([product("a"), product("b"), product("c")], "light_stroller")
        self.assertNotIn("price", benchmark["participants"][0])
        self.assertEqual(aggregate_prices([])["median"], None)


if __name__ == "__main__": unittest.main()
