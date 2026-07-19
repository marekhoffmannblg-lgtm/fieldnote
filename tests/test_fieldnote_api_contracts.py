"""Local API integration checks; all endpoints read existing offline data."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))

import app as api  # noqa: E402


class ApiContractTests(unittest.TestCase):
    def test_health_never_exposes_secret_values(self):
        payload = api.health()
        self.assertEqual(set(payload), {"openai_configured", "firecrawl_configured"})
        self.assertTrue(all(isinstance(value, bool) for value in payload.values()))

    def test_catalog_and_product_are_versioned_and_paginated(self):
        catalog = api.list_products(limit=3, offset=0)
        self.assertEqual(catalog["schema_version"], "1")
        self.assertEqual(catalog["total"], len(api.frontend_catalog()))
        self.assertLessEqual(len(catalog["items"]), 3)
        product = api.get_product("cybex__orfeo")
        self.assertEqual(product["schema_version"], "1")
        self.assertEqual(product["product_slug"], "cybex__orfeo")

    def test_product_sources_and_evidence_are_paginated(self):
        sources = api.product_sources("cybex__orfeo", limit=2, offset=0)
        self.assertEqual(sources["schema_version"], "1")
        self.assertEqual((sources["selected_count"], sources["fetched_count"], sources["failed_count"]), (10, 8, 2))
        self.assertLessEqual(len(sources["items"]), 2)
        evidence = api.product_evidence("cybex__orfeo", limit=5, offset=0)
        self.assertEqual(evidence["schema_version"], "1")
        self.assertLessEqual(len(evidence["items"]), 5)

    def test_runs_and_global_sources_are_versioned(self):
        runs = api.list_runs(limit=2, offset=0)
        sources = api.sources_catalog(limit=2, offset=0)
        self.assertEqual(runs["schema_version"], "1")
        self.assertEqual(sources["schema_version"], "1")
        self.assertLessEqual(len(runs["items"]), 2)
        self.assertLessEqual(len(sources["items"]), 2)


if __name__ == "__main__":
    unittest.main()
