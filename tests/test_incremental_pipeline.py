from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))
from services.benchmark_rebuild_service import BenchmarkRebuildService, benchmark_group_scope, product_scope, semantic_hash  # noqa: E402


def fixture() -> dict:
    return {
        "products": [
            {"product_id": "orf", "product_slug": "orf eo", "group_key": "lionelo|orfeo", "benchmark_group": "compact" , "price": 100},
            {"product_id": "neb", "product_slug": "nebo", "group_key": "lionelo|nebo", "benchmark_group": "compact", "price": 200},
        ],
        "sources": [{"source_id": "s-orf", "product_id": "orf"}, {"source_id": "s-neb", "product_id": "neb"}],
        "evidence": [{"evidence_id": "e-orf", "product_id": "orf", "value": "fold"}, {"evidence_id": "e-neb", "product_id": "neb", "value": "hood"}],
        "competitive_benchmarks": [{"benchmark_id": "cb-1", "anchor_product_id": "orf", "participant_product_ids": ["orf", "competitor"]}, {"benchmark_id": "cb-2", "anchor_product_id": "neb", "participant_product_ids": ["neb", "competitor"]}],
        "internal_benchmarks": [{"benchmark_group": "compact", "product_ids": ["orf", "neb"]}],
        "benchmark_snapshots": [],
        "competitive_benchmark_snapshots": [],
    }


class IncrementalPipelineTests(unittest.TestCase):
    def test_product_scope_contains_only_affected_records(self):
        state = fixture()
        scope = product_scope(state, "orf")
        self.assertEqual([item["product_id"] for item in scope["products"]], ["orf"])
        self.assertEqual([item["source_id"] for item in scope["sources"]], ["s-orf"])
        self.assertEqual([item["benchmark_id"] for item in scope["competitive_benchmarks"]], ["cb-1"])
        self.assertEqual(benchmark_group_scope(state, "compact")["product_ids"], ["neb", "orf"])

    def test_rebuild_orfeo_preserves_nebo_semantic_state(self):
        state = fixture()
        before = semantic_hash({"product": state["products"][1], "source": state["sources"][1], "evidence": state["evidence"][1]})
        with tempfile.TemporaryDirectory() as directory:
            result = BenchmarkRebuildService(lock_root=Path(directory)).rebuild_product_scope(state, "orf", updates={"price": 105}, run_id="run-orf")
        after_state = result.state
        after = semantic_hash({"product": after_state["products"][1], "source": after_state["sources"][1], "evidence": after_state["evidence"][1]})
        self.assertEqual(before, after)
        self.assertEqual(result.metadata["product_id"], "orf")
        self.assertEqual(len(after_state["benchmark_snapshots"]), 1)
        self.assertEqual([item["scope_id"] for item in after_state["competitive_benchmark_snapshots"]], ["cb-1"])


if __name__ == "__main__":
    unittest.main()
