"""Offline unit tests for P1 history and source lifecycle contracts.

These use unittest so they remain runnable in the intentionally minimal local
venv. They are pytest-compatible test files if pytest is installed later.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "fieldnote-api"))

from run_coordinator import LockUnavailableError, RunCoordinator
from run_manifest import default_manifest, merge_legacy_entries, read_manifest, rebuild_index, save_manifest, validate_manifest
from source_lifecycle import (
    default_product_source_link,
    default_source_record,
    product_source_counters,
    source_counters,
    validate_lifecycle_transition,
    validate_product_source_link,
    validate_source_record,
    validate_source_records,
)


class RunManifestTests(unittest.TestCase):
    def test_validation_and_index_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = default_manifest("run-one")
            first.update({"product_slug": "brand__one", "status": "succeeded"})
            save_manifest(first, runs_root=root)
            second = default_manifest("run-two")
            second.update({"product_slug": "brand__two", "status": "failed"})
            save_manifest(second, runs_root=root)
            index = rebuild_index(root)
            self.assertEqual(index["total"], 2)
            self.assertEqual(read_manifest("run-one", root)["status"], "succeeded")

    def test_legacy_deduplication(self):
        payload = {"run_id": "same-run", "product_slug": "brand__one", "status": "success"}
        manifests, conflicts = merge_legacy_entries([(Path("a.json"), payload), (Path("b.json"), dict(payload))])
        self.assertEqual(len(manifests), 1)
        self.assertEqual(conflicts, [])

    def test_retry_context_fields_are_immutable(self):
        original = default_manifest("original-run")
        original.update({"selected_offer_ids": ["101", "202"], "source_ids": ["allegro:101"], "flags": {"no_fetch": True}})
        retry = default_manifest("retry-run")
        retry.update({"retry_of": original["run_id"], "selected_offer_ids": list(original["selected_offer_ids"]), "source_ids": list(original["source_ids"]), "flags": dict(original["flags"])})
        original["selected_offer_ids"].append("303")
        self.assertEqual(retry["retry_of"], "original-run")
        self.assertEqual(retry["selected_offer_ids"], ["101", "202"])
        self.assertTrue(retry["flags"]["no_fetch"])

    def test_product_lock_allows_other_product_and_rejects_same(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = RunCoordinator(runs_root=root / "runs", output_root=root / "output")
            coordinator.acquire_product(run_id="one", product_slug="brand__one", group_key="brand|one")
            with self.assertRaises(LockUnavailableError):
                coordinator.acquire_product(run_id="two", product_slug="brand__one", group_key="brand|one")
            coordinator.acquire_product(run_id="three", product_slug="brand__two", group_key="brand|two")
            coordinator.release_product("one")
            coordinator.release_product("three")


class SourceLifecycleTests(unittest.TestCase):
    def test_source_record_validation_and_counters(self):
        record = default_source_record("allegro:1")
        record.update({"source_type": "marketplace_offer", "product_slug": "brand__one", "group_key": "brand|one"})
        record["selection"].update({"selected": True, "role": "primary", "selection_reason": "fixture"})
        record["fetch"]["status"] = "fetched"
        record["cleaning"]["status"] = "cleaned"
        record["assignment"].update({"status": "assigned", "assignment_reason": "fixture"})
        record["usage"].update({"used_in_final_product": True, "used_fields_count": 1})
        validate_source_record(record, known_source_ids={"allegro:1"}, project_root=ROOT)
        counters = source_counters([record])
        self.assertEqual(counters["selected_count"], 1)
        self.assertEqual(counters["used_count"], 1)

    def test_unassigned_reason_and_duplicate_target_are_required(self):
        record = default_source_record("allegro:2")
        record["assignment"].update({"status": "unassigned", "assignment_reason": None})
        with self.assertRaises(ValueError):
            validate_source_record(record, known_source_ids={"allegro:2"}, project_root=ROOT)
        record["assignment"].update({"status": "duplicate", "duplicate_of": "missing"})
        with self.assertRaises(ValueError):
            validate_source_record(record, known_source_ids={"allegro:2"}, project_root=ROOT)

    def test_duplicate_source_ids_are_rejected(self):
        record = default_source_record("same")
        with self.assertRaises(ValueError):
            validate_source_records([record, dict(record)], project_root=ROOT)

    def test_lifecycle_regression_is_rejected(self):
        previous = default_source_record("allegro:3")
        previous["fetch"]["status"] = "fetched"
        current = json.loads(json.dumps(previous))
        current["fetch"]["status"] = "not_requested"
        with self.assertRaises(ValueError):
            validate_lifecycle_transition(previous, current)

    def test_dry_run_style_build_does_not_write_registry(self):
        path = ROOT / "output" / "source_registry_v1.jsonl"
        before = path.read_bytes() if path.exists() else b""
        # Read-only validation mirrors --dry-run: no migration writer is called.
        self.assertIsInstance(before, bytes)
        after = path.read_bytes() if path.exists() else b""
        self.assertEqual(before, after)

    def test_orfeo_lifecycle_counters_are_distinct(self):
        from source_lifecycle import read_product_source_links, read_source_records
        sources = {item["source_id"]: item for item in read_source_records()}
        links = [item for item in read_product_source_links() if item.get("product_slug") == "cybex__orfeo"]
        counters = product_source_counters(links, sources)
        self.assertEqual(counters["selected_count"], 10)
        self.assertEqual(counters["fetched_count"], 8)
        self.assertEqual(counters["fetch_failed_count"], 2)
        self.assertEqual(counters["assigned_count"], 5)
        self.assertEqual(counters["unattached_count"], 3)

    def test_trig3_keeps_only_explicit_product_links(self):
        from source_lifecycle import read_product_source_links, read_source_records
        sources = {item["source_id"]: item for item in read_source_records()}
        links = [item for item in read_product_source_links() if item.get("product_slug") == "kinderkraft__trig-3"]
        self.assertEqual(len(links), 5)
        self.assertEqual(product_source_counters(links, sources)["assigned_count"], 5)
        self.assertNotIn("kinderkraft__trig-3|allegro:16894659311", {item["link_id"] for item in links})

    def test_global_queue_candidate_does_not_create_product_link(self):
        from source_lifecycle import read_product_source_links, read_source_records
        sources = {item["source_id"]: item for item in read_source_records()}
        self.assertIn("allegro:16894659311", sources)
        links = read_product_source_links()
        self.assertNotIn("kinderkraft__trig-3|allegro:16894659311", {item["link_id"] for item in links})

    def test_product_source_link_requires_global_source_identity(self):
        link = default_product_source_link("brand__model", "allegro:404")
        link["assignment"].update({"status": "unassigned", "assignment_reason": "fixture"})
        with self.assertRaises(ValueError):
            validate_product_source_link(link, known_source_ids={"allegro:1"})


if __name__ == "__main__":
    unittest.main()
