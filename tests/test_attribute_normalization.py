import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_relative_scoring import normalize_attribute, load_schema, score_products


class AttributeNormalizationTests(unittest.TestCase):
    def test_grams_to_kg(self):
        self.assertEqual(normalize_attribute({"value": "1850", "unit": "g"}, target_unit="kg", value_type="number"), 1.85)

    def test_mm_to_cm(self):
        self.assertEqual(normalize_attribute({"value": "420", "unit": "mm"}, target_unit="cm", value_type="number"), 42.0)

    def test_missing_is_none_not_zero(self):
        self.assertIsNone(normalize_attribute("unknown", target_unit="kg", value_type="number"))

    def test_boolean_polish_values(self):
        self.assertTrue(normalize_attribute("Tak", value_type="boolean"))
        self.assertFalse(normalize_attribute("Nie", value_type="boolean"))

    def test_schema_has_21_fields(self):
        self.assertEqual(len(load_schema()["attributes"]), 21)

    def test_polish_and_english_aliases_normalize_identically(self):
        products = [
            {"product_id": "pl", "benchmark_group": "g", "attributes": [{"key": "waga stelaża", "value": "1850", "unit": "g"}]},
            {"product_id": "en", "benchmark_group": "g", "attributes": [{"key": "frame weight", "value": "1.85", "unit": "kg"}]},
        ]
        result = score_products(products, group_key="g")
        self.assertEqual(result["participants"][0]["score"], result["participants"][1]["score"])


if __name__ == "__main__": unittest.main()
