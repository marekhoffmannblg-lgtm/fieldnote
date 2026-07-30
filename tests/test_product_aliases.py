from __future__ import annotations

import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
