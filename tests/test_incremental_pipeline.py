from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))
sys.path.insert(0, str(ROOT / "scripts"))
from services.benchmark_rebuild_service import BenchmarkRebuildService, benchmark_group_scope, product_scope, semantic_hash  # noqa: E402
from build_model_benchmark import merge_scoped_rows as merge_benchmark_rows  # noqa: E402
from report_model_coverage import merge_scoped_rows as merge_coverage_rows  # noqa: E402
import run_model_research_pipeline as research_pipeline  # noqa: E402
from run_model_research_pipeline import derived_stage_commands, source_price_median  # noqa: E402


def fixture() -> dict:
    return {
        "products": [
            {"product_id": "orf", "product_slug": "orf eo", "group_key": "lionelo|orfeo", "benchmark_group": "compact" , "price": 100},
            {"product_id": "neb", "product_slug": "nebo", "group_key": "lionelo|nebo", "benchmark_group": "compact", "price": 200},
            {"product_id": "trail", "product_slug": "trail", "group_key": "lionelo|trail", "benchmark_group": "terrain", "price": 300},
        ],
        "sources": [{"source_id": "s-orf", "product_id": "orf"}, {"source_id": "s-neb", "product_id": "neb"}],
        "evidence": [{"evidence_id": "e-orf", "product_id": "orf", "value": "fold"}, {"evidence_id": "e-neb", "product_id": "neb", "value": "hood"}],
        "competitive_benchmarks": [{"benchmark_id": "cb-1", "anchor_product_id": "orf", "participant_product_ids": ["orf", "competitor"]}, {"benchmark_id": "cb-2", "anchor_product_id": "neb", "participant_product_ids": ["neb", "competitor"]}],
        "internal_benchmarks": [{"benchmark_group": "compact", "product_ids": ["orf", "neb"]}, {"benchmark_group": "terrain", "product_ids": ["trail"]}],
        "benchmark_snapshots": [],
        "benchmark_group_snapshots": [{"scope_id": "terrain", "semantic_hash": "before"}],
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
        self.assertEqual(next(item for item in after_state["benchmark_group_snapshots"] if item["scope_id"] == "terrain")["semantic_hash"], "before")

    def test_canonical_derived_commands_are_always_scoped_and_never_export_frontend(self):
        benchmark, coverage = derived_stage_commands("lionelo|orfeo")
        self.assertEqual(benchmark[-2:], ["--group-key", "lionelo|orfeo"])
        self.assertEqual(coverage[-2:], ["--group-key", "lionelo|orfeo"])
        self.assertNotIn("export_frontend_snapshot.py", " ".join(benchmark + coverage))

    def test_price_median_is_derived_from_the_scoped_sources_only(self):
        self.assertEqual(
            source_price_median({"sources": [{"price": "999,00 zł"}, {"gross_price": "1 199.00 PLN"}, {"price": "0"}]}),
            1099.0,
        )

    def test_scoped_commit_payload_preserves_source_price_before_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_dir = root / "output" / "model_groups" / "orfeo"
            model_dir.mkdir(parents=True)
            (model_dir / "group.json").write_text(
                '{"group_key":"lionelo|orfeo","benchmark_group":"compact","sources":[{"source_id":"s1","price":100},{"source_id":"s2","price":105}]}',
                encoding="utf-8",
            )
            (model_dir / "model_state.json").write_text('{"group_key":"lionelo|orfeo","fields":{}}', encoding="utf-8")
            with patch.object(research_pipeline, "ROOT", root):
                payload = research_pipeline.scoped_commit_payload(
                    "lionelo|orfeo", {"product_id": "orf"}, {"benchmark_group": "compact"}
                )
        self.assertEqual(payload["price_median"], 102.5)
        self.assertEqual(payload["semantic_state"]["price_median"], 102.5)

    def test_direct_cli_without_context_keeps_derived_stages_scoped(self):
        calls = []

        class History:
            run_id = "direct-cli-test"
            payload = {"finished_at": ""}
            def update_summary(self, **_kwargs): pass
            def update_latest_stage(self, *_args): pass
            def complete(self, status, **_kwargs): self.payload["finished_at"] = status
            def save(self): pass

        def fake_stage(number, _label, command=None, *_args, **_kwargs):
            calls.append((number, command))
            return ("", 0)

        args = Namespace(
            marketplace="allegro", brand="Lionelo", model="Orfeo", category_key="stroller",
            benchmark_group="compact", apply=True, resume=False, skip_ai=True,
            skip_product_profile=True, retry_errors=True, fixture_scenario=None,
            fixture_root=None, run_context=None, cancel_check_file=None,
        )
        product = {"product_id": "orf", "category_key": "stroller", "benchmark_group": "compact"}
        with patch.object(research_pipeline, "parse_args", return_value=args), \
             patch.object(research_pipeline, "ResearchRun", return_value=History()), \
             patch.object(research_pipeline, "product_for_group_key", return_value=product), \
             patch.object(research_pipeline, "validate_category_assignment", return_value={"category_key": "stroller", "benchmark_group": "compact"}), \
             patch.object(research_pipeline, "ensure_catalog_product", return_value=product), \
             patch.object(research_pipeline, "ensure_group_directory", return_value=research_pipeline.ROOT), \
             patch.object(research_pipeline, "retry_offer_ids_for_model", return_value=set()), \
             patch.object(research_pipeline, "coverage_for_group", return_value={"group_key": "lionelo|orfeo"}), \
             patch.object(research_pipeline, "run_stage", side_effect=fake_stage), \
             patch.object(research_pipeline, "FileLock", side_effect=lambda *_args, **_kwargs: nullcontext()), \
             patch.object(research_pipeline, "print_pipeline_summary"):
            self.assertEqual(research_pipeline.main(), 0)
        derived = {number: command for number, command in calls if number in {8, 9}}
        self.assertEqual(derived[8][-2:], ["--group-key", "lionelo|orfeo"])
        self.assertEqual(derived[9][-2:], ["--group-key", "lionelo|orfeo"])
        self.assertNotIn("export_frontend_snapshot.py", " ".join(derived[8] + derived[9]))

    def test_requested_ineligible_scope_removes_stale_derived_rows(self):
        existing = [{"group_key": "lionelo|orfeo"}, {"group_key": "lionelo|nebo"}]
        self.assertEqual(merge_benchmark_rows(existing, [], {"lionelo|orfeo"}), [{"group_key": "lionelo|nebo"}])
        self.assertEqual(merge_coverage_rows(existing, [], {"lionelo|orfeo"}), [{"group_key": "lionelo|nebo"}])


if __name__ == "__main__":
    unittest.main()
