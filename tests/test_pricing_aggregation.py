import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fieldnote-api"))
from services.pricing_service import aggregate_prices


class PricingAggregationTests(unittest.TestCase):
    def test_same_seller_across_channels_counts_once(self):
        result = aggregate_prices([
            {"seller_id":"shop-a", "price":1000, "source_id":"allegro"},
            {"seller_id":"shop-a", "price":1100, "source_id":"amazon"},
            {"seller_id":"shop-b", "price":1200, "source_id":"retail"},
        ])
        self.assertEqual(result["seller_count"], 2)
        self.assertEqual(result["min"], 1100)
        self.assertEqual(result["max"], 1200)

    def test_invalid_and_empty_prices_are_ignored(self):
        self.assertEqual(aggregate_prices([{"seller":"x", "price":"N/D"}])["status"], "no_data")


if __name__ == "__main__": unittest.main()
