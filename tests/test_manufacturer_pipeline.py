from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from manufacturer_pipeline import normalized_document_from_fixture  # noqa: E402


class ManufacturerPipelineTests(unittest.TestCase):
    def metadata(self, *, model: str = "NEBO", url: str = "https://kinderkraft.pl/nebo"):
        return {"source_id": "manufacturer:kinderkraft:nebo", "brand": "Kinderkraft", "model": model,
                "title": f"Kinderkraft {model}", "canonical_url": url, "model_match": True,
                "source_type": "manufacturer_product_page", "json_ld": {"sku": "NEBO-PL"}}

    def test_cleaner_and_normalization_keep_technical_facts(self):
        text = "Kinderkraft NEBO\nWaga produktu: 7,5 kg\nMaksymalne obciążenie: 22 kg\nWymiary po złożeniu: 51 × 43 × 21 cm\nPolecane produkty\nInny model"
        document = normalized_document_from_fixture(self.metadata(), text)
        self.assertTrue(document.model_match)
        self.assertNotIn("Polecane", document.clean_text)
        self.assertEqual({fact.field_candidate for fact in document.facts}, {"Waga", "Udźwig", "Wymiary po złożeniu", "SKU"})

    def test_identity_mismatch_blocks_extraction(self):
        document = normalized_document_from_fixture(self.metadata(model="NEBO"), "Kinderkraft NEA\nWaga: 7 kg")
        self.assertFalse(document.model_match)
        self.assertFalse(document.facts)
        self.assertIn("identity_mismatch_blocks_extraction", document.warnings)

    def test_optional_accessories_are_not_facts(self):
        document = normalized_document_from_fixture(self.metadata(), "Kinderkraft NEBO\nOpcjonalne akcesoria: torba\nWaga: 7 kg")
        self.assertNotIn("Akcesoria", {fact.field_candidate for fact in document.facts})

    def test_cybex_fixture_uses_the_same_normalized_document(self):
        metadata = {
            "source_id": "manufacturer:cybex:orfeo", "brand": "CYBEX", "model": "ORFEO",
            "title": "CYBEX ORFEO", "canonical_url": "https://cybex-online.com/orfeo",
            "model_match": True, "source_type": "manufacturer_product_page",
        }
        document = normalized_document_from_fixture(metadata, "CYBEX ORFEO\nWaga: 6,3 kg\nDealer locator\nInny model")
        self.assertTrue(document.model_match)
        self.assertEqual(document.authority, "manufacturer")
        self.assertEqual(document.facts[0].field_candidate, "Waga")
        self.assertNotIn("Dealer", document.clean_text)


if __name__ == "__main__":
    unittest.main()
