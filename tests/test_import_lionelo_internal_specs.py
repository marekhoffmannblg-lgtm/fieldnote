#!/usr/bin/env python3
"""Offline regression tests for the internal Lionelo specification importer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from import_lionelo_internal_specs import build_snapshots, validate_snapshots  # noqa: E402


class InternalSpecsImporterTest(unittest.TestCase):
    def test_matches_single_stroller_configuration_and_records_variant_conflict(self) -> None:
        product = {
            "product_id": "product:lionelo:test",
            "slug": "lionelo__test",
            "brand": "Lionelo",
            "model": "Test",
            "configuration": "",
            "benchmark_group": "light_stroller",
        }
        rows = [
            [],
            ["Identyfikacja", "Parametry / techniczne", "Funkcjonalność"],
            ["model", "Waga stelaża (kg)", "Składanie jedną ręką"],
            [],
            [],
            ["Test", "7,5", "Tak"],
            ["Test", "8,0", "Tak"],
        ]
        # The fixture deliberately uses the worksheet's descriptive configuration
        # column in a separate minimal table to cover the catalog equivalence.
        rows[1].insert(1, "Parametry / techniczne")
        rows[2].insert(1, "Konfiguracja wózka")
        rows[5].insert(1, "Spacerówka")
        rows[6].insert(1, "Spacerówka")

        snapshots, unmatched = build_snapshots([product], rows, "2026-01-01T00:00:00Z")
        snapshot = snapshots["lionelo__test"]
        self.assertEqual(unmatched, [])
        self.assertEqual(snapshot["source_rows"], [6, 7])
        self.assertEqual(snapshot["attributes"][1]["value"], "conflicting")
        self.assertEqual(snapshot["attributes"][2]["value"], "yes")
        self.assertEqual(snapshot["conflicts"][0]["key"], "frame_weight")

    def test_full_validation_requires_all_34_catalog_snapshots(self) -> None:
        with self.assertRaisesRegex(ValueError, "dokładnie 34"):
            validate_snapshots({}, [])


if __name__ == "__main__":
    unittest.main()
