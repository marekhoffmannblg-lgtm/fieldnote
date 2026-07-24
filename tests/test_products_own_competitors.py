from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from migrate_competitor_stroller_taxonomy import migrate  # noqa: E402


class OwnCompetitorCatalogTests(unittest.TestCase):
    def test_classified_competitor_is_normalized_without_losing_research_fields(self) -> None:
        original = {
            "brand": "Bugaboo", "model": "Butterfly 2", "category_key": "stroller", "benchmark_group": "light_stroller",
            "product_id": "product:bugaboo:butterfly-2", "slug": "bugaboo__butterfly-2", "group_key": "bugaboo|butterfly 2",
            "coverage": 52.38, "snapshot_path": "output/snapshot.json", "evidence_count": 8,
        }
        products, changed = migrate([original])
        migrated = products[0]
        self.assertEqual(changed, 1)
        self.assertEqual((migrated["category_key"], migrated["subcategory_key"], migrated["subcategory"]), ("mobility", "strollers", "Wózki"))
        for key in ("product_id", "slug", "group_key", "coverage", "snapshot_path", "evidence_count", "benchmark_group"):
            self.assertEqual(migrated[key], original[key])

    def test_unclassified_record_remains_hidden_from_main_catalogue(self) -> None:
        original = {"brand": "Kinderkraft", "model": "Accessory", "category_key": "stroller", "benchmark_group": ""}
        products, changed = migrate([original])
        self.assertEqual(changed, 0)
        self.assertEqual(products[0], original)


if __name__ == "__main__":
    unittest.main()
