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


if __name__ == "__main__":
    unittest.main()
