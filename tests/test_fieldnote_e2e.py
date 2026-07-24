"""Offline fixture E2E checks for FIELDNOTE's public lifecycle contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from source_adapters import AllegroAdapter, FixtureAdapter, ManufacturerAdapter, adapter_manifest  # noqa: E402
from source_lifecycle import product_source_counters, read_product_source_links, read_source_records  # noqa: E402


class FixtureE2ETests(unittest.TestCase):
    def test_fixture_pipeline_scenarios_are_offline_and_isolated(self):
        for scenario, expected in (("success", "success"), ("partial", "partial"), ("failed", "failed"), ("empty_results", "preview")):
            with tempfile.TemporaryDirectory() as directory:
                fixture_root = Path(directory) / "fixture"
                fixture_root.mkdir()
                command = [
                    sys.executable, str(ROOT / "scripts" / "run_model_research_pipeline.py"),
                    "--marketplace", "allegro", "--brand", "Demo", "--model", "Sprint",
                    "--fixture-scenario", scenario, "--fixture-root", str(fixture_root),
                ]
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 1 if scenario == "failed" else 0, result.stderr)
                self.assertIn(f"pipeline_status={expected}", result.stdout)
                manifests = list((fixture_root / "output" / "research_runs").glob("*.json"))
                self.assertTrue(manifests)

    def test_existing_listing_is_discovered_without_network(self):
        adapter = AllegroAdapter()
        candidates = adapter.discover("Kinderkraft NEBO", {"listing_dir": ROOT / "input" / "targeted_search" / "kinderkraft__nebo" / "allegro"})
        self.assertTrue(candidates)
        self.assertTrue(all(item.marketplace == "allegro" for item in candidates))
        self.assertFalse(adapter.fetch(candidates[0], {}).status == "fetched")

    def test_fixture_and_manufacturer_adapter_contracts(self):
        fixture = FixtureAdapter()
        candidates = fixture.discover("Demo", {"fixture_path": ROOT / "fixtures" / "e2e" / "source_candidates.json"})
        self.assertEqual(len(candidates), 1)
        self.assertTrue(adapter_manifest(fixture)["capabilities"]["discovery"])
        self.assertTrue(adapter_manifest(ManufacturerAdapter())["capabilities"]["manufacturer_specifications"])

    def test_product_lifecycle_and_unanalysed_snapshot(self):
        sources = {item["source_id"]: item for item in read_source_records()}
        links = [item for item in read_product_source_links() if item.get("product_slug") == "cybex__orfeo"]
        counters = product_source_counters(links, sources)
        self.assertEqual((counters["selected_count"], counters["fetched_count"], counters["fetch_failed_count"]), (10, 8, 2))
        apino = json.loads((ROOT / "fieldnote-frontend" / "src" / "data" / "generated" / "products" / "kinderkraft__apino.json").read_text(encoding="utf-8"))
        # APINO can legitimately gain coverage after a local resume. The
        # contract is that an unavailable analysis is represented by null,
        # while an available one carries numeric metrics.
        if apino.get("coverage") is None:
            self.assertIsNone(apino.get("missing_fields_count"))
        else:
            self.assertIsInstance(apino.get("coverage"), (int, float))
            self.assertTrue(apino.get("missing_fields_count") is None or isinstance(apino.get("missing_fields_count"), int))

    def test_documented_failure_and_recovery_contracts_exist(self):
        app = (ROOT / "fieldnote-api" / "app.py").read_text(encoding="utf-8")
        self.assertIn('/api/runs/{run_id}/cancel', app)
        self.assertIn('/api/runs/{run_id}/retry', app)
        self.assertIn('recover_interrupted_runs', app)


if __name__ == "__main__":
    unittest.main()
