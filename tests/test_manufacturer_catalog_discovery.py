from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discover_manufacturer_catalog import discover_catalog, load_source_config  # noqa: E402


class ManufacturerCatalogTests(unittest.TestCase):
    def test_fixture_catalog_excludes_accessory_and_classifies_real_records(self):
        report = discover_catalog(brand="Kinderkraft", fixture_root=ROOT / "fixtures" / "firecrawl" / "manufacturer")
        self.assertEqual(report["quality_gate"], "pass")
        self.assertEqual(report["counts"]["unclassified_real_products"], 0)
        self.assertGreaterEqual(report["counts"]["excluded"], 1)
        active = [item for item in report["items"] if item.get("catalog_status") != "excluded"]
        self.assertEqual({item["model"] for item in active}, {"NEBO", "NUBI 2"})

    def test_config_has_only_allowed_external_channels(self):
        config = load_source_config()
        self.assertEqual(config["category"], "strollers")
        allowed = {"allegro.pl", "amazon.pl"}
        for source in config["sources"]:
            self.assertTrue(set(source["retailers"]).issubset(allowed))

    def test_discovery_report_is_serializable(self):
        report = discover_catalog(brand="Kinderkraft", fixture_root=ROOT / "fixtures" / "firecrawl" / "manufacturer")
        json.dumps(report, ensure_ascii=False)

    def test_unclassified_real_product_blocks_quality_gate(self):
        root = Path(tempfile.mkdtemp())
        (root / "catalog.json").write_text(json.dumps({"products": [{"brand": "Brand", "model": "Future", "title": "Brand Future stroller"}]}), encoding="utf-8")
        report = discover_catalog(brand="Brand", fixture_root=root)
        self.assertEqual(report["counts"]["review_required"], 1)
        self.assertEqual(report["counts"]["unclassified_real_products"], 1)
        self.assertEqual(report["quality_gate"], "review")


if __name__ == "__main__":
    unittest.main()
