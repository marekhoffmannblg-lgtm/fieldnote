from __future__ import annotations

import sys
import unittest
from itertools import permutations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from normalize_product_aliases import canonical_product_key, normalize_alias, normalize_records  # noqa: E402


class ProductAliasTests(unittest.TestCase):
    def test_configurations_are_not_merged(self):
        self.assertNotEqual(canonical_product_key("Brand", "Combi", "2w1"), canonical_product_key("Brand", "Combi", "3w1"))

    def test_colour_variants_share_identity(self):
        self.assertEqual(normalize_alias("Kinderkraft NEBO black", brand="Kinderkraft", model="NEBO"), normalize_alias("Kinderkraft NEBO white", brand="Kinderkraft", model="NEBO"))

    def test_aliases_merge_only_same_canonical_product(self):
        records = normalize_records([
            {"brand": "Brand", "model": "Combi", "configuration": "2w1", "title": "Brand Combi black"},
            {"brand": "Brand", "model": "Combi", "configuration": "2w1", "title": "Brand Combi white"},
            {"brand": "Brand", "model": "Combi", "configuration": "3w1", "title": "Brand Combi 3w1"},
        ])
        self.assertEqual(len(records), 2)
        self.assertEqual(sorted(item["configuration"] for item in records), ["2w1", "3w1"])
        two = next(item for item in records if item["configuration"] == "2w1")
        self.assertEqual(len(two["aliases"]), 2)

    def test_title_only_colour_variants_merge(self):
        records = normalize_records([
            {"brand": "Brand", "title": "Brand Combi Black"},
            {"brand": "Brand", "title": "Brand Combi White"},
        ])
        self.assertEqual(len(records), 1)

    def test_title_only_configurations_stay_separate(self):
        records = normalize_records([
            {"brand": "Brand", "title": "Brand Combi 2w1"},
            {"brand": "Brand", "title": "Brand Combi 3w1"},
        ])
        self.assertEqual({item["configuration"] for item in records}, {"2w1", "3w1"})

    def test_three_duplicate_conflicting_groups_are_order_independent(self):
        cards = [
            {"brand": "Brand", "model": "Combi", "title": "Brand Combi Black", "benchmark_group": "light_stroller"},
            {"brand": "Brand", "model": "Combi", "title": "Brand Combi White", "benchmark_group": "standard_stroller"},
            {"brand": "Brand", "model": "Combi", "title": "Brand Combi Red", "benchmark_group": "light_stroller"},
        ]
        results = {
            (
                normalize_records(list(order))[0]["catalog_status"],
                normalize_records(list(order))[0]["classification_reason"],
            )
            for order in permutations(cards)
        }
        self.assertEqual(results, {("review_required", "conflicting_benchmark_groups")})

    def test_duplicate_source_ids_include_singular_and_existing_values(self):
        records = normalize_records([
            {"brand": "Brand", "model": "Combi", "source_id": "official:white"},
            {"brand": "Brand", "model": "Combi", "source_id": "official:black", "source_ids": ["retailer:one"]},
        ])
        self.assertEqual(records[0]["source_ids"], ["official:black", "official:white", "retailer:one"])
        self.assertEqual(records[0]["source_id"], "official:black")

    def test_conflicting_group_fields_are_order_independent(self):
        cards = [
            {
                "brand": "Brand",
                "model": "Combi",
                "title": "Brand Combi Black",
                "benchmark_group": "light_stroller",
                "benchmark_group_key": "standard_stroller",
                "catalog_status": "classified",
            },
            {
                "brand": "Brand",
                "model": "Combi",
                "title": "Brand Combi White",
                "benchmark_group": "light_stroller",
                "catalog_status": "classified",
            },
        ]
        outcomes = set()
        for order in permutations(cards):
            merged = normalize_records(list(order))[0]
            outcomes.add((merged["catalog_status"], merged["classification_reason"]))

        self.assertEqual(
            outcomes,
            {("review_required", "conflicting_benchmark_groups")},
        )


if __name__ == "__main__":
    unittest.main()
