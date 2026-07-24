from __future__ import annotations

import sys
import tempfile
import unittest
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "fieldnote-api"))

import app as fieldnote_api  # noqa: E402
from fetch_targeted_model_offers import classify_model_match  # noqa: E402


class OfferMatchClassificationTests(unittest.TestCase):
    def status(self, requested_brand: str, requested_model: str, title: str) -> tuple[str, str]:
        status, reason, _brand_match, _model_match = classify_model_match(
            title=title,
            brand=requested_brand,
            model=requested_model,
            category_key="stroller",
            product_type="stroller",
        )
        return status, reason

    def test_equivalent_superscript_and_spaced_generation_is_exact(self) -> None:
        self.assertEqual(self.status("Joolz", "Aer²", "Joolz Aer 2"), ("exact_match", ""))

    def test_missing_year_is_probable(self) -> None:
        self.assertEqual(self.status("CYBEX", "Coya 2025", "CYBEX Coya"), ("probable_match", "missing_year_token"))

    def test_missing_generation_is_probable(self) -> None:
        self.assertEqual(self.status("Bugaboo", "Butterfly 2", "Bugaboo Butterfly"), ("probable_match", "missing_generation_token"))

    def test_conflicting_generation_is_rejected(self) -> None:
        self.assertEqual(self.status("Bugaboo", "Butterfly 2", "Bugaboo Butterfly 3"), ("rejected", "conflicting_generation"))

    def test_accessory_and_other_brand_are_rejected(self) -> None:
        accessory = classify_model_match(
            title="torba Bugaboo Butterfly 2", brand="Bugaboo", model="Butterfly 2",
            category_key="stroller", product_type="accessory",
        )
        self.assertEqual(accessory[:2], ("rejected", "accessory"))
        self.assertEqual(self.status("Bugaboo", "Butterfly 2", "Joolz Butterfly 2"), ("rejected", "brand_mismatch"))

    def test_probable_offer_is_selectable_but_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "extracted_offers.json").write_text(
                '[{"offer_id":"123456789","title":"Brand Model Wózek","product_type":"stroller","brand_match":true,"model_match":false,"match_status":"probable_match","rejection_reason":"missing_generation_token","canonical_url":"https://allegro.pl/oferta/example-123456789"}]',
                encoding="utf-8",
            )
            (directory / "rejected_offers.json").write_text("[]", encoding="utf-8")
            (directory / "research_summary.json").write_text("{}", encoding="utf-8")
            offers, _summary = fieldnote_api.read_preview_offers("Brand", "Model 2", "stroller", directory=directory)
        self.assertEqual(offers[0]["match_status"], "probable_match")
        self.assertTrue(offers[0]["selectable"])
        self.assertFalse(offers[0]["accepted"])

    def test_classifier_has_no_product_specific_conditions(self) -> None:
        classifier_source = inspect.getsource(classify_model_match).lower()
        for product_name in ("joolz", "coya", "bugaboo", "butterfly"):
            self.assertNotIn(product_name, classifier_source)


if __name__ == "__main__":
    unittest.main()
