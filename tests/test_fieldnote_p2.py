"""Offline P2 provenance and UI-contract regression tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from provenance_v1 import (  # noqa: E402
    aggregate_field,
    build_evidence_item,
    load_product_provenance,
    product_metrics,
    source_content_family,
)
from source_lifecycle import product_source_counters, read_product_source_links, read_source_records  # noqa: E402


def source(source_id: str, content_hash: str = "", source_type: str = "marketplace_offer") -> dict:
    return {
        "source_id": source_id,
        "source_type": source_type,
        "marketplace": "manufacturer" if source_type == "manufacturer" else "allegro",
        "content": {"content_hash": content_hash, "content_family_id": ""},
        "metadata": {"offer_quality_score": 50},
        "first_seen_at": "2026-01-01T00:00:00Z",
    }


class ProvenanceV1Tests(unittest.TestCase):
    def test_legacy_evidence_is_unattributed_and_not_valid(self):
        item = build_evidence_item(
            product_slug="brand__model", field_name="Waga", current_value="6 kg",
            raw={"source_id": "", "value": "6 kg", "excerpt": "Waga: 6 kg", "validation_status": "valid"}, index=0,
            source_by_id={}, link_by_source={}, field_validation="valid",
        )
        self.assertEqual(item["evidence_status"], "unattributed_legacy")
        self.assertEqual(item["confirmation_weight"], 0.0)

    def test_missing_source_reference_is_rejected(self):
        item = build_evidence_item(
            product_slug="brand__model", field_name="Waga", current_value="6 kg",
            raw={"source_id": "allegro:missing", "value": "6 kg", "excerpt": "Waga: 6 kg", "validation_status": "valid"}, index=0,
            source_by_id={}, link_by_source={}, field_validation="valid",
        )
        self.assertEqual(item["validation_status"], "invalid_reference")
        self.assertEqual(item["evidence_status"], "rejected")

    def test_identical_hashes_are_one_content_family(self):
        self.assertEqual(source_content_family(source("allegro:1", "same")), source_content_family(source("allegro:2", "same")))

    def test_same_family_is_not_two_independent_confirmations(self):
        items = [
            {"evidence_id": "a", "evidence_status": "valid", "content_family_id": "family:one", "source_id": "manufacturer:1", "confirmation_weight": 1.0, "fetched_at": "2026-01-02", "source_quality": 100, "normalized_value": "stal"},
            {"evidence_id": "b", "evidence_status": "valid", "content_family_id": "family:one", "source_id": "allegro:1", "confirmation_weight": 0.7, "fetched_at": "2026-01-01", "source_quality": 70, "normalized_value": "stal"},
        ]
        aggregate = aggregate_field(items, "stal")
        self.assertEqual(aggregate["independent_confirmations_count"], 1)

    def test_independent_sources_increase_confirmation_count_and_primary_is_stable(self):
        items = [
            {"evidence_id": "market", "evidence_status": "valid", "content_family_id": "market", "source_id": "allegro:1", "confirmation_weight": 0.7, "fetched_at": "2026-01-01", "source_quality": 99, "normalized_value": "stal"},
            {"evidence_id": "manufacturer", "evidence_status": "valid", "content_family_id": "manufacturer", "source_id": "manufacturer:1", "confirmation_weight": 1.0, "fetched_at": "2026-02-01", "source_quality": 1, "normalized_value": "stal"},
        ]
        aggregate = aggregate_field(list(reversed(items)), "stal")
        self.assertEqual(aggregate["primary_evidence_id"], "manufacturer")
        self.assertEqual(aggregate["independent_confirmations_count"], 2)

    def test_unanalysed_metrics_are_null_not_zero_missing(self):
        metrics = product_metrics({}, {}, False)
        self.assertIsNone(metrics["coverage_percent"])
        self.assertIsNone(metrics["missing_fields"])

    def test_coverage_and_evidence_quality_are_separate(self):
        fields = {
            "Marka": {"value": "A", "validation_status": "valid", "confidence": "high", "evidence_v1": []},
            "Model": {"value": "B", "validation_status": "weak", "confidence": "medium", "evidence_v1": []},
        }
        aggregates = {"Marka": {"primary_evidence_id": "one"}, "Model": {"primary_evidence_id": "two"}}
        metrics = product_metrics(fields, aggregates, True)
        self.assertGreater(metrics["coverage_percent"], metrics["evidence_quality_percent"])

    def test_orfeo_counters_and_persisted_provenance(self):
        sources = {item["source_id"]: item for item in read_source_records()}
        links = [item for item in read_product_source_links() if item.get("product_slug") == "cybex__orfeo"]
        counters = product_source_counters(links, sources)
        self.assertEqual((counters["selected_count"], counters["fetched_count"], counters["fetch_failed_count"], counters["assigned_count"], counters["unattached_count"]), (10, 8, 2, 5, 3))
        self.assertTrue(load_product_provenance("cybex__orfeo").get("fields"))

    def test_production_navigation_has_no_mock_integrations(self):
        app = (ROOT / "fieldnote-frontend" / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertNotIn('{ id: "integracje"', app)
        self.assertNotIn("Jan Kowalski", app)


if __name__ == "__main__":
    unittest.main()
