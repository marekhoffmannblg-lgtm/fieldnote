from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import catalog_registry as catalog  # noqa: E402
import import_lionelo_strollers as importer  # noqa: E402


class LioneloStrollerImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.original_paths = (catalog.PRODUCTS_PATH, catalog.BRANDS_PATH, catalog.CATEGORIES_PATH)
        catalog.PRODUCTS_PATH, catalog.BRANDS_PATH, catalog.CATEGORIES_PATH = root / "products.json", root / "brands.json", root / "categories.json"
        for path in (catalog.PRODUCTS_PATH, catalog.BRANDS_PATH, catalog.CATEGORIES_PATH):
            path.write_text("[]", encoding="utf-8")
        self.rows = importer.matching_rows(ROOT / "output" / "taxonomy" / "FIELDNOTE_product_inventory_classified.csv")
        self.labels = importer.registry_labels(ROOT / "output" / "taxonomy" / "category_registry.json")

    def tearDown(self) -> None:
        catalog.PRODUCTS_PATH, catalog.BRANDS_PATH, catalog.CATEGORIES_PATH = self.original_paths
        self.temp.cleanup()

    def test_import_is_idempotent_and_preserves_configurations(self) -> None:
        first = importer.import_rows(self.rows, self.labels)
        products = json.loads(catalog.PRODUCTS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(first, Counter({"CREATE": 34}))
        self.assertEqual(len(products), 34)
        self.assertEqual(Counter(product["benchmark_group"] for product in products), Counter({"light_stroller": 10, "stroller_3in1": 9, "stroller_2in1": 8, "standard_stroller": 7}))
        self.assertEqual(importer.import_rows(self.rows, self.labels), Counter({"SKIP": 34}))
        amber = [product for product in products if product["model"] == "Amber"]
        self.assertEqual({product["configuration"] for product in amber}, {"2w1", "3w1"})
        mika_plus = [product for product in products if product["model"] == "Mika Plus"]
        self.assertEqual({product["configuration"] for product in mika_plus}, {"", "2w1", "3w1"})
        self.assertTrue(all(product["scope"] == "production" for product in products))

    def test_conflicting_existing_classification_is_not_overwritten(self) -> None:
        row = next(item for item in self.rows if item["model"] == "Amber" and item["configuration"] == "2w1")
        catalog.ensure_catalog_product("Lionelo", "Amber", category_key="mobility", subcategory_key="strollers", benchmark_group="light_stroller", configuration="2w1", scope="production")
        outcomes = importer.import_rows([row], self.labels)
        self.assertEqual(outcomes, Counter({"CONFLICT": 1}))


if __name__ == "__main__":
    unittest.main()
