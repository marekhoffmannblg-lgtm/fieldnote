from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))
from p0_runtime import LockUnavailableError  # noqa: E402
from services.benchmark_rebuild_service import BenchmarkRebuildService, price_change_requires_snapshot, semantic_hash  # noqa: E402


def fixture() -> dict:
    return {
        "products": [
            {"product_id": "orf", "product_slug": "orf eo", "group_key": "lionelo|orfeo", "benchmark_group": "compact", "price": 100},
            {"product_id": "neb", "product_slug": "nebo", "group_key": "lionelo|nebo", "benchmark_group": "compact", "price": 200},
        ],
        "sources": [{"source_id": "s-orf", "product_id": "orf"}, {"source_id": "s-neb", "product_id": "neb"}],
        "evidence": [{"evidence_id": "e-orf", "product_id": "orf", "value": "fold"}, {"evidence_id": "e-neb", "product_id": "neb", "value": "hood"}],
        "competitive_benchmarks": [{"benchmark_id": "cb-1", "anchor_product_id": "orf", "participant_product_ids": ["orf", "competitor"]}, {"benchmark_id": "cb-2", "anchor_product_id": "neb", "participant_product_ids": ["neb", "competitor"]}],
        "internal_benchmarks": [{"benchmark_group": "compact", "product_ids": ["orf", "neb"]}],
        "benchmark_snapshots": [],
        "competitive_benchmark_snapshots": [],
    }


class IncrementalBenchmarkRebuildTests(unittest.TestCase):
    def test_price_threshold_is_strictly_five_percent(self):
        self.assertFalse(price_change_requires_snapshot(100, 104.99))
        self.assertTrue(price_change_requires_snapshot(100, 105))

    def test_unchanged_run_does_not_create_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            service = BenchmarkRebuildService(lock_root=Path(directory))
            first = service.rebuild_product_scope(fixture(), "orf", run_id="one")
            second = service.rebuild_product_scope(first.state, "orf", run_id="two")
        self.assertTrue(first.metadata["snapshot_created"])
        self.assertFalse(second.metadata["snapshot_created"])
        self.assertEqual(len(second.state["benchmark_snapshots"]), 1)

    def test_small_price_change_does_not_create_snapshot_but_five_percent_does(self):
        with tempfile.TemporaryDirectory() as directory:
            service = BenchmarkRebuildService(lock_root=Path(directory))
            first = service.rebuild_product_scope(fixture(), "orf", run_id="one")
            small = service.rebuild_product_scope(first.state, "orf", updates={"price": 104.99}, run_id="small")
            large = service.rebuild_product_scope(small.state, "orf", updates={"price": 105}, run_id="large")
        self.assertFalse(small.metadata["snapshot_created"])
        self.assertTrue(large.metadata["snapshot_created"])

    def test_admin_full_rebuild_matches_accumulated_scopes(self):
        initial = fixture()
        with tempfile.TemporaryDirectory() as directory:
            service = BenchmarkRebuildService(lock_root=Path(directory))
            incremental = service.rebuild_product_scope(initial, "orf", updates={"price": 105}, run_id="orf").state
            incremental = service.rebuild_product_scope(incremental, "neb", updates={"price": 210}, run_id="neb").state
            full = service.rebuild_all_admin(fixture(), run_id="full").state
            full["products"][0]["price"] = 105
            full["products"][1]["price"] = 210
            full = service.rebuild_all_admin(full, run_id="full-2").state
        self.assertEqual(semantic_hash(incremental), semantic_hash(full))

    def test_global_admin_lock_blocks_scoped_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_root = Path(directory)
            (lock_root / "aggregation.lock").write_text('{"run_id":"admin"}\n', encoding="utf-8")
            with self.assertRaises(LockUnavailableError):
                BenchmarkRebuildService(lock_root=lock_root).rebuild_product_scope(fixture(), "orf")


if __name__ == "__main__":
    unittest.main()
