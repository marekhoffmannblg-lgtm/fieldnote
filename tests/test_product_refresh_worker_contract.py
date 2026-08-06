import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fieldnote-api"))
from services.pipeline_service import PipelineService
from services.job_service import JobService
from services.pipeline_service import PipelineResult
from worker import ResearchWorker


class RefreshDouble:
    def refresh(self, **kwargs):
        return {"status": "succeeded", "result": {"sources": [{"source_id": "allegro:1"}]}}


class Jobs:
    def create(self, value): return value


class Products:
    def product(self, slug): return {"product_id": "p1", "brand": "Lionelo", "model": "Amber", "configuration": "3w1", "category_key": "stroller", "benchmark_group": "stroller"}


class Queue:
    def __init__(self): self.done = []
    def claim(self, worker_id, lease_seconds, max_active): return {"job_id": "r1", "product_id": "p1", "lease_token": "tok", "payload": {"job_type": "product_refresh"}}
    def start(self, job_id, token): return {"job_id": job_id, "product_id": "p1", "lease_token": token, "payload": {"job_type": "product_refresh"}}
    def heartbeat(self, job_id, token, lease_seconds): return {"job_id": job_id}
    def complete(self, *args): self.done.append(args); return {"job_id": "r1", "status": args[2]}


class Committer:
    def __init__(self): self.calls = []
    def complete(self, job, token, status, result, usage, cost): self.calls.append((status, result)); return {"status": status}


class ProductRefreshWorkerContractTests(unittest.TestCase):
    def test_typed_refresh_bypasses_legacy_resume_and_returns_terminal_result(self):
        pipeline = PipelineService(refresh_service=RefreshDouble())
        result = pipeline.execute({"job_id": "r1", "product_id": "p1", "payload": {"job_type": "product_refresh", "product_slug": "lionelo__amber", "brand": "Lionelo", "model": "Amber", "configuration": "3w1"}}, cancel_check_file=Path("/tmp/fieldnote-no-cancel"))
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.usage["pages"], 1)

    def test_typed_refresh_fails_closed_without_worker_adapter(self):
        result = PipelineService().execute({"payload": {"job_type": "product_refresh"}}, cancel_check_file=Path("/tmp/fieldnote-no-cancel"))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "product_refresh_not_configured")

    def test_job_service_persists_typed_refresh_payload(self):
        job = JobService(Jobs(), Products()).enqueue(product_slug="lionelo__amber", requested_by="u1", job_type="product_refresh")
        self.assertEqual(job["payload"]["job_type"], "product_refresh")
        self.assertEqual(job["payload"]["configuration"], "3w1")

    def test_worker_terminalizes_refresh_without_scoped_commit_as_partial(self):
        queue, committer = Queue(), Committer()
        pipeline = type("Pipeline", (), {"execute": lambda self, job, cancel_check_file: PipelineResult("succeeded", {"usage_complete": True}, {"sources": []})})()
        self.assertTrue(ResearchWorker(queue, pipeline, committer=committer).process_one())
        self.assertEqual(committer.calls[0][0], "partial")
        self.assertTrue(committer.calls[0][1]["no_mutation"])


if __name__ == "__main__": unittest.main()
