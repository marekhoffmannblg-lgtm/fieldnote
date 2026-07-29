from __future__ import annotations

import sys
import tempfile
import threading
import unittest
import json
import csv
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))
sys.path.insert(0, str(ROOT / "scripts"))
from p0_runtime import LockUnavailableError  # noqa: E402
from services.benchmark_rebuild_service import BenchmarkRebuildService, price_change_requires_snapshot, semantic_hash  # noqa: E402
from services.benchmark_commit_service import BenchmarkCommitService  # noqa: E402
from services.pipeline_service import PipelineResult  # noqa: E402
from worker import ResearchWorker  # noqa: E402
import build_model_benchmark  # noqa: E402
import report_model_coverage  # noqa: E402


def fixture() -> dict:
    return {
        "products": [
            {"product_id": "orf", "product_slug": "orf eo", "group_key": "lionelo|orfeo", "benchmark_group": "compact", "price": 100},
            {"product_id": "neb", "product_slug": "nebo", "group_key": "lionelo|nebo", "benchmark_group": "compact", "price": 200},
            {"product_id": "trail", "product_slug": "trail", "group_key": "lionelo|trail", "benchmark_group": "terrain", "price": 300},
        ],
        "sources": [{"source_id": "s-orf", "product_id": "orf"}, {"source_id": "s-neb", "product_id": "neb"}],
        "evidence": [{"evidence_id": "e-orf", "product_id": "orf", "value": "fold"}, {"evidence_id": "e-neb", "product_id": "neb", "value": "hood"}],
        "competitive_benchmarks": [{"benchmark_id": "cb-1", "anchor_product_id": "orf", "participant_product_ids": ["orf", "competitor"]}, {"benchmark_id": "cb-2", "anchor_product_id": "neb", "participant_product_ids": ["neb", "competitor"]}],
        "internal_benchmarks": [{"benchmark_group": "compact", "product_ids": ["orf", "neb"]}, {"benchmark_group": "terrain", "product_ids": ["trail"]}],
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
            incremental = service.rebuild_product_scope(incremental, "trail", run_id="trail").state
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

    def test_fixture_transactions_serialize_two_scopes_and_admin_without_lost_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "seed.json", root / "state.json"
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            service = BenchmarkRebuildService(lock_root=root / "locks")
            barrier, errors = threading.Barrier(4), []

            def rebuild(product_id, price):
                try:
                    barrier.wait()
                    service.rebuild_product_state_file(source, target, product_id, updates={"price": price}, run_id=product_id)
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(exc)

            first = threading.Thread(target=rebuild, args=("orf", 105))
            second = threading.Thread(target=rebuild, args=("neb", 210))
            def admin_rebuild():
                try:
                    barrier.wait()
                    service.rebuild_all_admin_state_file(source, target, run_id="admin")
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(exc)
            admin = threading.Thread(target=admin_rebuild)
            first.start(); second.start(); admin.start(); barrier.wait(); first.join(); second.join(); admin.join()
            self.assertEqual(errors, [])
            state = json.loads(target.read_text(encoding="utf-8"))
            prices = {item["product_id"]: item["price"] for item in state["products"]}
            self.assertEqual(prices, {"orf": 105, "neb": 210, "trail": 300})
            self.assertEqual({run["run_id"] for run in state["research_runs"]}, {"orf", "neb", "admin"})

    def test_commit_envelope_applies_the_price_threshold_to_durable_product_snapshot(self):
        job = {"job_id": "job", "product_id": "orf"}
        def payload(price):
            return {"scoped_commit": {"scope": {"product_id": "orf", "group_key": "lionelo|orfeo", "benchmark_group": "compact"}, "semantic_state": {"fields": {"weight": "7"}, "price_median": price}, "price_median": price}}
        low = BenchmarkCommitService(object())._snapshots(job, payload(104.99)["scoped_commit"])[0][0]
        high = BenchmarkCommitService(object())._snapshots(job, payload(105)["scoped_commit"])[0][0]
        self.assertEqual(low["price_median"], 104.99)
        self.assertEqual(high["price_median"], 105.0)
        self.assertFalse(price_change_requires_snapshot(100, low["price_median"]))
        self.assertTrue(price_change_requires_snapshot(100, high["price_median"]))

    def test_worker_does_not_report_success_when_durable_incremental_commit_fails(self):
        class Pipeline:
            def execute(self, _job, *, cancel_check_file):
                return PipelineResult("succeeded", {"pages": 1, "ai_tokens": 0, "usage_complete": True}, {"scoped_commit": {"scope": {"product_id": "orf", "group_key": "lionelo|orfeo", "benchmark_group": "compact"}, "semantic_state": {"fields": {"weight": "7"}}}})
        class Jobs:
            def __init__(self): self.completed = []
            def claim(self, *_args, **_kwargs): return {"job_id": "job", "lease_token": "token", "product_id": "orf", "payload": {"limits": {}}}
            def start(self, *_args): return {"job_id": "job", "lease_token": "token", "product_id": "orf", "payload": {"limits": {}}}
            def heartbeat(self, *_args): return {"job_id": "job"}
            def complete_incremental(self, *_args): return {}
            def complete(self, *_args): self.completed.append(_args); return {"job_id": "job"}
        jobs = Jobs()
        self.assertFalse(ResearchWorker(jobs, Pipeline()).process_one())
        self.assertEqual(jobs.completed, [])

    def test_worker_preserves_no_mutation_partial_through_fenced_incremental_path(self):
        class Pipeline:
            def execute(self, _job, *, cancel_check_file):
                return PipelineResult("partial", {"pages": 11, "usage_complete": False}, {"reason": "max_pages_exceeded_before_start"})
        class Jobs:
            def __init__(self): self.incremental = []; self.completed = []
            def claim(self, *_args, **_kwargs): return {"job_id": "job", "lease_token": "token", "product_id": "orf", "payload": {"limits": {}}}
            def start(self, *_args): return {"job_id": "job", "lease_token": "token", "product_id": "orf", "payload": {"limits": {}}}
            def heartbeat(self, *_args): return {"job_id": "job"}
            def complete_incremental(self, *args): self.incremental.append(args); return {"job_id": "job", "status": "partial"}
            def complete(self, *args): self.completed.append(args); return {"job_id": "job"}
        jobs = Jobs()
        self.assertTrue(ResearchWorker(jobs, Pipeline()).process_one())
        self.assertEqual(len(jobs.incremental), 1)
        self.assertEqual(jobs.incremental[0][2], "partial")
        self.assertEqual(jobs.incremental[0][-1], [])
        self.assertEqual(jobs.incremental[0][-2]["no_mutation"], True)
        self.assertEqual(jobs.completed, [])

    def test_builder_commands_remove_stale_rows_for_ineligible_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            groups = root / "model_groups" / "orfeo"
            groups.mkdir(parents=True)
            (groups / "group.json").write_text(json.dumps({
                "group_key": "lionelo|orfeo", "taxonomy_status": "review_required",
                "benchmark_category": "", "taxonomy_version": "v1", "sources": [],
            }), encoding="utf-8")
            (groups / "model_state.json").write_text(json.dumps({
                "group_key": "lionelo|orfeo", "brand": "Lionelo", "model": "Orfeo", "fields": {},
            }), encoding="utf-8")
            existing_benchmark = root / "model_benchmark.csv"
            existing_sources = root / "model_benchmark_sources.csv"
            existing_coverage = root / "model_coverage.csv"
            for path, fields in (
                (existing_benchmark, ["group_key", "category"]),
                (existing_sources, ["group_key", "source_id"]),
                (existing_coverage, ["group_key", "coverage_percent"]),
            ):
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
                    writer.writerow({fields[0]: "lionelo|orfeo", fields[1]: "stale"})
                    writer.writerow({fields[0]: "lionelo|nebo", fields[1]: "keep"})
            with patch.object(build_model_benchmark, "GROUPS", root / "model_groups"), patch.object(build_model_benchmark, "OUT", root), \
                 patch.object(report_model_coverage, "GROUPS", root / "model_groups"), patch.object(report_model_coverage, "OUT", root), \
                 patch.object(build_model_benchmark, "atomic_write_json", lambda path, value: path.write_text(json.dumps(value), encoding="utf-8")), \
                 patch.object(report_model_coverage, "atomic_write_json", lambda path, value: path.write_text(json.dumps(value), encoding="utf-8")):
                with patch("sys.argv", ["build_model_benchmark.py", "--group-key", "lionelo|orfeo"]):
                    self.assertEqual(build_model_benchmark.main(), 0)
                with patch("sys.argv", ["report_model_coverage.py", "--group-key", "lionelo|orfeo"]):
                    self.assertEqual(report_model_coverage.main(), 0)
            for path in (existing_benchmark, existing_sources):
                with path.open(encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual([row["group_key"] for row in rows], ["lionelo|nebo"])
            with existing_coverage.open(encoding="utf-8", newline="") as handle:
                coverage_rows = list(csv.DictReader(handle))
            self.assertEqual({row["group_key"] for row in coverage_rows}, {"lionelo|nebo", "lionelo|orfeo"})
            self.assertNotIn("stale", {row.get("coverage_percent", "") for row in coverage_rows})


if __name__ == "__main__":
    unittest.main()
