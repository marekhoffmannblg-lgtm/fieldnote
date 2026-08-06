import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fieldnote-api"))
from services.pipeline_service import PipelineService
from services.job_service import JobService
from services.pipeline_service import PipelineResult
from services.product_refresh_service import MemoryRefreshHistory, MemoryRefreshStorage, ProductRefreshService
from worker import ResearchWorker


class RefreshDouble:
    def __init__(self, result=None): self.kwargs = {}; self.result = result
    def refresh(self, **kwargs):
        self.kwargs = kwargs
        return self.result or {"status": "succeeded", "result": {"sources": [{"source_id": "allegro:1"}]}}


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


class IncrementalQueue(Queue):
    def __init__(self): super().__init__(); self.incremental = []
    def claim(self, worker_id, lease_seconds, max_active):
        return {"job_id": "r1", "product_id": "p1", "lease_token": "tok", "payload": {"job_type": "product_refresh", "brand": "Lionelo", "model": "Amber", "configuration": "3w1", "benchmark_group": "stroller", "limits": {}}}
    def start(self, job_id, token): return self.claim("", 0, 0)
    def complete_incremental(self, *args): self.incremental.append(args); return {"job_id": "r1", "status": args[2]}


class Committer:
    def __init__(self): self.calls = []
    def complete(self, job, token, status, result, usage, cost): self.calls.append((status, result)); return {"status": status}


class FixtureRefreshProvider:
    def search(self, query, *, limit):
        return {"data": {"items": [{"url": "https://allegro.pl/oferta/amber-real", "title": "Lionelo Amber 3w1 stroller", "offer_id": "real"}]}}

    def scrape(self, url):
        return {"data": {"markdown": "Waga: 9,5 kg Maksymalne obciążenie: 22 kg"}}


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

    def test_typed_refresh_preserves_exact_product_configuration_and_product_only_scope(self):
        envelope = {"status": "succeeded", "result": {"sources": [{"source_id": "allegro:1"}], "scoped_commit": {"scope": {"product_id": "p1", "group_key": "lionelo|amber", "benchmark_group": "stroller", "configuration": "3w1", "participant_product_ids": ["p1"]}, "semantic_state": {"facts": {"waga_wozka_kg": 9.5}, "evidence": [], "sources": ["allegro:1"]}}}}
        queue, refresh = IncrementalQueue(), RefreshDouble(envelope)
        self.assertTrue(ResearchWorker(queue, PipelineService(refresh_service=refresh)).process_one())
        self.assertEqual(refresh.kwargs["configuration"], "3w1")
        scope, snapshots = queue.incremental[0][6], queue.incremental[0][7]
        self.assertEqual(scope["product_id"], "p1"); self.assertEqual(scope["configuration"], "3w1")
        self.assertEqual(scope["participant_product_ids"], ["p1"])
        self.assertEqual([snapshot["scope_type"] for snapshot in snapshots], ["product"])

    def test_real_refresh_service_output_commits_only_product_scope(self):
        queue = IncrementalQueue()
        refresh = ProductRefreshService(FixtureRefreshProvider(), MemoryRefreshStorage(), MemoryRefreshHistory())
        self.assertTrue(ResearchWorker(queue, PipelineService(refresh_service=refresh)).process_one())
        scope, snapshots = queue.incremental[0][6], queue.incremental[0][7]
        self.assertEqual(scope["product_id"], "p1")
        self.assertEqual(scope["participant_product_ids"], ["p1"])
        self.assertEqual([snapshot["scope_type"] for snapshot in snapshots], ["product"])
        self.assertEqual(snapshots[0]["payload"]["state"]["facts"]["waga_wozka_kg"], 9.5)

    def test_real_partial_refresh_is_fenced_no_mutation(self):
        queue = IncrementalQueue()
        refresh = ProductRefreshService(ProviderWithoutCapacity(), MemoryRefreshStorage(), MemoryRefreshHistory())
        self.assertTrue(ResearchWorker(queue, PipelineService(refresh_service=refresh)).process_one())
        self.assertEqual(queue.incremental[0][2], "partial")
        self.assertTrue(queue.incremental[0][6]["no_mutation"])
        self.assertEqual(queue.incremental[0][7], [])


class ProviderWithoutCapacity(FixtureRefreshProvider):
    def scrape(self, url):
        return {"data": {"markdown": "Waga: 9,5 kg"}}


if __name__ == "__main__": unittest.main()
