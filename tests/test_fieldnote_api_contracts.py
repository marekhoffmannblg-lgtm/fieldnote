"""Local API integration checks; all endpoints read existing offline data."""

from __future__ import annotations

import sys
import subprocess
import unittest
import inspect
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))

import app as api  # noqa: E402


class ApiContractTests(unittest.TestCase):
    def preview_request(self, mode: str = "live") -> api.PreviewRequest:
        return api.PreviewRequest(brand="Fixture", model="Light", category_key="stroller", benchmark_group="light_stroller", search_mode=mode)

    def preview_patches(self):
        return {
            "product_for_group_key": patch.object(api, "product_for_group_key", return_value={}),
            "manufacturer_sources_for": patch.object(api, "manufacturer_sources_for", return_value=[]),
            "read_preview_offers": patch.object(api, "read_preview_offers", return_value=([], {})),
        }

    def test_preview_defaults_to_live(self):
        self.assertEqual(api.PreviewRequest(brand="Fixture", model="Light", category_key="stroller", benchmark_group="light_stroller").search_mode, "live")

    def test_live_search_calls_provider_even_when_cache_exists_and_updates_cache(self):
        cached = {"directory": ROOT / "fixture-cache", "cached_at": "2026-01-01T00:00:00+00:00", "legacy": False}
        completed = subprocess.CompletedProcess(["fetch"], 0, "", "")
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"}, clear=False), patch.object(api, "product_for_group_key", return_value={}), patch.object(api, "manufacturer_sources_for", return_value=[]), patch.object(api, "cached_listing_info", return_value=cached), patch.object(api, "run_command", return_value=completed) as run, patch.object(api, "cache_listing_artifacts", return_value="2026-01-02T00:00:00+00:00") as save, patch.object(api, "read_preview_offers", return_value=([], {})):
            result = api.research_preview(self.preview_request())
        self.assertEqual(result["result_mode"], "live_firecrawl")
        self.assertTrue(result["is_fresh"])
        run.assert_called_once()
        self.assertNotIn("--input-html", run.call_args.args[0])
        save.assert_called_once()

    def test_live_failure_never_returns_cached_offers(self):
        cached = {"directory": ROOT / "fixture-cache", "cached_at": "2026-01-01T00:00:00+00:00", "legacy": False}
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"}, clear=False), patch.object(api, "product_for_group_key", return_value={}), patch.object(api, "manufacturer_sources_for", return_value=[]), patch.object(api, "cached_listing_info", return_value=cached), patch.object(api, "run_command", return_value=subprocess.CompletedProcess(["fetch"], 1, "", "failed")):
            result = api.research_preview(self.preview_request())
        self.assertEqual(result["status"], "LIVE_SEARCH_FAILED")
        self.assertEqual(result["offers"], [])
        self.assertTrue(result["cached_result_available"])

    def test_cache_mode_uses_cache_without_provider_and_reports_missing_cache(self):
        cached = {"directory": ROOT / "fixture-cache", "cached_at": "2026-01-01T00:00:00+00:00", "legacy": False}
        with patch.object(api, "product_for_group_key", return_value={}), patch.object(api, "manufacturer_sources_for", return_value=[]), patch.object(api, "cached_listing_info", return_value=cached), patch.object(api.Path, "is_file", return_value=True), patch.object(api, "read_json", return_value={"match_classification_version": "3"}), patch.object(api, "read_preview_offers", return_value=([], {})), patch.object(api, "run_command") as run:
            result = api.research_preview(self.preview_request("cache"))
        self.assertEqual(result["result_mode"], "local_cache")
        self.assertFalse(result["is_fresh"])
        run.assert_not_called()
        with patch.object(api, "product_for_group_key", return_value={}), patch.object(api, "manufacturer_sources_for", return_value=[]), patch.object(api, "cached_listing_info", return_value=None):
            missing = api.research_preview(self.preview_request("cache"))
        self.assertEqual(missing["status"], "CACHE_NOT_AVAILABLE")

    def test_listing_cache_is_category_scoped(self):
        self.assertNotEqual(
            api.listing_cache_dir("Fixture", "Light", "allegro", "stroller"),
            api.listing_cache_dir("Fixture", "Light", "allegro", "other_category"),
        )
    def test_source_runner_finalization_runs_profile_once_and_preserves_partial_states(self):
        payload = {"run_id": "fixture-run", "product_slug": "brand__model", "logs": []}
        runner_success = subprocess.CompletedProcess(["runner"], 0, "new_offers=2\npipeline_status=success\n", "")
        with patch.object(api, "generate_profile_for_owned_run", return_value="generated") as profile, patch.object(api, "export_snapshot_for_owned_run", return_value=True) as snapshot:
            self.assertEqual(api.finalize_source_run(payload, "fixture-run", api.pipeline_status_from_result(runner_success)), "success")
        profile.assert_called_once_with(payload, "fixture-run")
        snapshot.assert_called_once_with(payload, "fixture-run", 97)

        timeout = subprocess.CompletedProcess(
            ["cascade"], 20,
            "source_analysis_status=failed\nsource_analysis_error_code=source_analysis_timeout\n",
            "",
        )
        self.assertTrue(api.controlled_analysis_timeout(timeout))
        self.assertEqual(api.pipeline_status_from_result(timeout), "partial")
        with patch.object(api, "generate_profile_for_owned_run", return_value="cached"), patch.object(api, "export_snapshot_for_owned_run", return_value=True):
            self.assertEqual(api.finalize_source_run(payload, "fixture-run", "partial"), "partial")
        with patch.object(api, "generate_profile_for_owned_run", return_value="failed"), patch.object(api, "export_snapshot_for_owned_run", return_value=True):
            self.assertEqual(api.finalize_source_run(payload, "fixture-run", "success"), "partial")
        with patch.object(api, "generate_profile_for_owned_run", return_value="generated"), patch.object(api, "export_snapshot_for_owned_run", return_value=False):
            self.assertEqual(api.finalize_source_run(payload, "fixture-run", "success"), "partial")

    def test_partial_pipeline_status_is_never_persisted_as_succeeded(self):
        payload = {"status": "succeeded", "pipeline_status": "partial"}
        self.assertEqual(api.normalize_terminal_run_status(payload)["status"], "partial")

    def test_finalize_persists_terminal_status_before_snapshot_export(self):
        payload = {"run_id": "fixture-run", "product_slug": "brand__model", "logs": []}
        calls: list[str] = []

        def record_status(*_args: object, **_kwargs: object) -> None:
            calls.append("status")

        def record_snapshot(*_args: object, **_kwargs: object) -> bool:
            calls.append("snapshot")
            return True

        with patch.object(api, "generate_profile_for_owned_run", return_value="skipped"), patch.object(api, "set_product_analysis_status", side_effect=record_status), patch.object(api, "export_snapshot_for_owned_run", side_effect=record_snapshot):
            self.assertEqual(api.finalize_source_run(payload, "fixture-run", "success"), "partial")
        self.assertEqual(calls, ["status", "snapshot"])

    def test_health_never_exposes_secret_values(self):
        payload = api.health()
        self.assertEqual(set(payload), {"openai_configured", "firecrawl_configured"})
        self.assertTrue(all(isinstance(value, bool) for value in payload.values()))

    def test_logged_command_reaches_terminal_result_without_pipe_wait_deadlock(self):
        payload = {"run_id": "fixture-command", "logs": []}
        work_directory = ROOT / "output" / "_FIELDNOTE_TEST_SESSION" / "fixture-command"
        with patch.object(api, "heartbeat_run"), patch.object(api, "read_run", return_value={}), patch.object(api.RUN_COORDINATOR, "work_directory", return_value=work_directory):
            result = api.logged_command(
                payload,
                "Proces testowy",
                50,
                [sys.executable, "-c", "print('child_finished')"],
            )
        self.assertEqual(result.returncode, 0)
        self.assertIn("child_finished", result.stdout)
        self.assertIsNone(payload["child_pid"])

    def test_catalog_and_product_are_versioned_and_paginated(self):
        catalog = api.list_products(limit=3, offset=0)
        self.assertEqual(catalog["schema_version"], "1")
        self.assertEqual(catalog["total"], len(api.frontend_catalog()))
        self.assertLessEqual(len(catalog["items"]), 3)
        product = api.get_product("cybex__orfeo")
        self.assertEqual(product["schema_version"], "1")
        self.assertEqual(product["product_slug"], "cybex__orfeo")

    def test_catalog_registration_is_idempotent_and_visible_without_snapshot(self):
        record = {
            "product_id": "product:ergobaby:metro-3", "brand": "Ergobaby", "model": "Metro 3",
            "group_key": "ergobaby|metro 3", "category": "Wózki dziecięce",
            "category_key": "stroller", "benchmark_group": "light_stroller", "created_at": "2026-01-01T00:00:00+00:00",
        }
        states: dict[str, dict[str, str]] = {}
        with patch.object(api, "load_products", return_value=[record]), patch.object(api.PRODUCT_SERVICE.snapshots, "catalog", return_value=[]), patch.object(api, "load_product_states", return_value=states):
            catalog = api.frontend_catalog()
            self.assertEqual([item["slug"] for item in catalog], ["ergobaby__metro-3"])
            self.assertEqual(catalog[0]["status"], "refresh_recommended")
            self.assertEqual(catalog[0]["status_reason"], "no_research_completed")

    def test_create_product_does_not_depend_on_exact_preview_match(self):
        created = {
            "product_id": "product:bugaboo:butterfly-2", "brand": "Bugaboo", "model": "Butterfly 2",
            "group_key": "bugaboo|butterfly 2", "category": "Wózki dziecięce",
            "category_key": "stroller", "benchmark_group": "light_stroller", "created_at": "2026-01-01T00:00:00+00:00",
        }
        request = api.ProductCreateRequest(brand="Bugaboo", model="Butterfly 2", category_key="stroller", benchmark_group="light_stroller")
        with patch.object(api, "load_products", return_value=[]), patch.object(api, "ensure_catalog_product", return_value=created) as ensure, patch.object(api, "update_product_state") as update, patch.object(api, "frontend_catalog", return_value=[{"slug": "bugaboo__butterfly-2", "brand": "Bugaboo", "model": "Butterfly 2", "status": "refresh_recommended"}]):
            result = api.create_product(request)
        self.assertTrue(result["created"])
        ensure.assert_called_once()
        update.assert_called_once_with("bugaboo__butterfly-2", "refresh_recommended", refresh_reason="no_research_completed")
        self.assertEqual(result["product"]["slug"], "bugaboo__butterfly-2")

    def test_registered_product_without_snapshot_has_a_normal_detail_response(self):
        record = {
            "product_id": "product:joolz:aer2", "brand": "Joolz", "model": "Aer²",
            "group_key": "joolz|aer2", "category": "Wózki dziecięce",
            "category_key": "stroller", "benchmark_group": "light_stroller", "created_at": "2026-01-01T00:00:00+00:00",
        }
        with patch.object(api, "load_products", return_value=[record]), patch.object(api.PRODUCT_SERVICE.snapshots, "catalog", return_value=[]), patch.object(api.PRODUCT_SERVICE, "detail", return_value=None), patch.object(api, "load_product_states", return_value={}):
            detail = api.get_product("joolz__aer2")
        self.assertEqual(detail["schema_version"], "1")
        self.assertEqual(detail["status"], "refresh_recommended")
        self.assertEqual(detail["fields"], [])
        self.assertFalse(detail["research_snapshot_available"])

    def test_registry_taxonomy_wins_in_list_and_detail_responses(self):
        record = {
            "product_id": "product:fixture:light", "brand": "Fixture", "model": "Light",
            "group_key": "fixture|light", "category": "Wózki", "category_key": "stroller",
            "benchmark_group": "light_stroller", "benchmark_category": "Lekkie spacerówki",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        stale_snapshot = {
            "slug": "fixture__light", "brand": "Fixture", "model": "Light", "group_key": "fixture|light",
            "status": "ready", "category": "Stara etykieta", "category_key": "legacy",
            "benchmark_group": "legacy_group", "benchmark_category": "Stara grupa",
        }
        expected = {"category": "Wózki", "category_key": "stroller", "benchmark_group": "light_stroller", "benchmark_category": "Lekkie spacerówki"}
        with patch.object(api, "load_products", return_value=[record]), patch.object(api.PRODUCT_SERVICE.snapshots, "catalog", return_value=[stale_snapshot]), patch.object(api.PRODUCT_SERVICE, "detail", return_value=dict(stale_snapshot)), patch.object(api, "load_product_states", return_value={}):
            listed = api.list_products(limit=10, offset=0)["items"][0]
            detailed = api.get_product("fixture__light")
        self.assertEqual({key: listed[key] for key in expected}, expected)
        self.assertEqual({key: detailed[key] for key in expected}, expected)

    def test_product_creation_uses_registry_labels_not_a_hardcoded_category(self):
        request = api.ProductCreateRequest(brand="Fixture", model="Light", category_key="stroller", benchmark_group="light_stroller")
        assignment = {"category_label": "Etykieta centralna", "benchmark_group_label": "Grupa centralna"}
        created = {"brand": "Fixture", "model": "Light", "group_key": "fixture|light"}
        with patch.object(api, "validate_category_assignment", return_value=assignment), patch.object(api, "load_products", return_value=[]), patch.object(api, "ensure_catalog_product", return_value=created) as ensure, patch.object(api, "update_product_state"), patch.object(api, "frontend_catalog", return_value=[]):
            api.create_product(request)
        self.assertEqual(ensure.call_args.kwargs["category"], "Etykieta centralna")
        self.assertEqual(ensure.call_args.kwargs["benchmark_category"], "Grupa centralna")
        self.assertNotIn('category="Wózki dziecięce"', inspect.getsource(api.create_product))

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
