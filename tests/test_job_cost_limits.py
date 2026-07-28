from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))

from services.pipeline_service import PipelineResult
from worker import ResearchWorker


class JobCostLimitTests(unittest.TestCase):
    def test_page_token_and_cost_limit_produce_partial_without_discarding_result(self):
        job = {"cost_limit": 1, "payload": {"limits": {"max_pages": 2, "max_ai_tokens": 5}}}
        result = PipelineResult("succeeded", {"pages": 3, "ai_tokens": 6, "cost_used": 2}, {"committed_sources": 1})
        self.assertEqual(ResearchWorker._final_status(job, result), "partial")
        self.assertEqual(result.result["committed_sources"], 1)

    def test_pipeline_timeout_is_partial_and_has_no_network_fixture_dependency(self):
        from services.pipeline_service import PipelineService
        import subprocess
        def timeout(*_, **__): raise subprocess.TimeoutExpired("fixture", 1)
        result = PipelineService(runner=timeout).execute({"payload": {"limits": {"timeout_seconds": 1}}}, cancel_check_file=ROOT / "fixtures" / "does-not-exist")
        self.assertEqual(result.status, "partial")
        self.assertTrue(result.usage["timeout"])


if __name__ == "__main__": unittest.main()
