from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "fieldnote-api"))

import catalog_registry as catalog  # noqa: E402
from benchmark_taxonomy import same_benchmark_partition  # noqa: E402
from category_registry import CategoryValidationError, supports_product_type, validate_category_assignment  # noqa: E402
import app as fieldnote_api  # noqa: E402
from fetch_targeted_model_offers import slug as targeted_slug  # noqa: E402


class CategoryFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.original_paths = (catalog.PRODUCTS_PATH, catalog.BRANDS_PATH, catalog.CATEGORIES_PATH)
        catalog.PRODUCTS_PATH = root / "products.json"
        catalog.BRANDS_PATH = root / "brands.json"
        catalog.CATEGORIES_PATH = root / "categories.json"
        for path in (catalog.PRODUCTS_PATH, catalog.BRANDS_PATH, catalog.CATEGORIES_PATH):
            path.write_text("[]", encoding="utf-8")

    def tearDown(self) -> None:
        catalog.PRODUCTS_PATH, catalog.BRANDS_PATH, catalog.CATEGORIES_PATH = self.original_paths
        self.temp.cleanup()

    def test_valid_stroller_assignment_is_saved(self) -> None:
        product = catalog.ensure_catalog_product(
            "Test Brand", "Test Model", category_key="stroller", benchmark_group="light_stroller"
        )
        saved = json.loads(catalog.PRODUCTS_PATH.read_text(encoding="utf-8"))[0]
        self.assertEqual(product["category_key"], "stroller")
        self.assertEqual(saved["benchmark_group"], "light_stroller")
        self.assertEqual(saved["category_classification_status"], "classified")

    def test_invalid_category_group_is_rejected(self) -> None:
        with self.assertRaises(CategoryValidationError) as context:
            validate_category_assignment("stroller", "not_a_real_group")
        self.assertEqual(context.exception.code, "INVALID_BENCHMARK_GROUP")

    def test_unknown_category_is_not_supported(self) -> None:
        with self.assertRaises(CategoryValidationError) as context:
            validate_category_assignment("power_tools", "drill")
        self.assertEqual(context.exception.code, "NOT_SUPPORTED")

    def test_different_groups_never_share_benchmark_partition(self) -> None:
        light = {"category_key": "stroller", "benchmark_group": "light_stroller", "slug": "anything"}
        standard = {"category_key": "stroller", "benchmark_group": "standard_stroller", "slug": "another"}
        self.assertFalse(same_benchmark_partition(light, standard))

    def test_category_adapter_controls_selectable_preview_offer(self) -> None:
        self.assertTrue(supports_product_type("stroller", "stroller"))
        self.assertFalse(supports_product_type("stroller", "accessory"))

    def test_preview_cache_key_includes_category_key(self) -> None:
        stroller = fieldnote_api.preview_cache_key("allegro", "Brand", "Model", "stroller")
        other_category = fieldnote_api.preview_cache_key("allegro", "Brand", "Model", "another-category")
        self.assertNotEqual(stroller, other_category)

    def test_preview_offer_selectable_is_adapter_owned(self) -> None:
        original_targeted_dir = fieldnote_api.targeted_dir
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "extracted_offers.json").write_text(json.dumps([{
                "offer_id": "123456789", "title": "Brand Model stroller", "product_type": "stroller",
                "brand_match": True, "model_match": True, "canonical_url": "https://allegro.pl/oferta/example-123456789",
            }]), encoding="utf-8")
            (directory / "rejected_offers.json").write_text("[]", encoding="utf-8")
            (directory / "research_summary.json").write_text("{}", encoding="utf-8")
            fieldnote_api.targeted_dir = lambda _brand, _model, _marketplace="allegro": directory
            try:
                offers, _summary = fieldnote_api.read_preview_offers("Brand", "Model", "stroller")
            finally:
                fieldnote_api.targeted_dir = original_targeted_dir
        self.assertTrue(offers[0]["category_compatible"])
        self.assertTrue(offers[0]["selectable"])

    def test_superscript_model_label_is_valid(self) -> None:
        self.assertEqual(fieldnote_api.validated_label("Aer²"), "Aer²")
        self.assertEqual(targeted_slug("Aer²"), "aer2")

    def test_existing_stroller_catalog_record_has_canonical_keys(self) -> None:
        products, _changed = catalog.migrate_product_category_fields(
            catalog.read_list(self.original_paths[0])
        )
        product = next(item for item in products if item.get("group_key") == "kinderkraft|nebo")
        self.assertEqual(product.get("category_key"), "mobility")
        self.assertEqual(product.get("benchmark_group"), "light_stroller")


if __name__ == "__main__":
    unittest.main()
