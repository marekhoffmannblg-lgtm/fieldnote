from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))

from services.pipeline_service import PipelineResult
from worker import ResearchWorker


class FakePipeline:
    def execute(self, _job, *, cancel_check_file):
        self.control_exists = cancel_check_file.exists()
        return PipelineResult("succeeded", {"pages": 1, "ai_tokens": 0}, {"fixture": True})


class LeasedJobs:
    def __init__(self, values): self.values, self.completed = values, []
    def claim(self, _worker, _lease, max_active):
        self.last_max_active = max_active
        return self.values.pop(0) if self.values else {}
    def start(self, job_id, token): return {"job_id": job_id, "lease_token": token, "payload": {"limits": {"max_pages": 10, "max_ai_tokens": 10}}}
    def heartbeat(self, job_id, token, _lease): return {"job_id": job_id, "lease_token": token}
    def complete(self, job_id, token, status, result, usage, cost):
        self.completed.append((job_id, token, status, result, usage, cost)); return {"job_id": job_id}


class WorkerLeaseTests(unittest.TestCase):
    def test_two_workers_claim_distinct_jobs_and_database_cap_is_passed(self):
        queue = LeasedJobs([
            {"job_id": "one", "lease_token": "token-1", "payload": {"limits": {"max_pages": 10, "max_ai_tokens": 10}}},
            {"job_id": "two", "lease_token": "token-2", "payload": {"limits": {"max_pages": 10, "max_ai_tokens": 10}}},
        ])
        one, two = ResearchWorker(queue, FakePipeline(), worker_id="a"), ResearchWorker(queue, FakePipeline(), worker_id="b")
        self.assertTrue(one.process_one()); self.assertTrue(two.process_one())
        self.assertEqual([item[0] for item in queue.completed], ["one", "two"])
        self.assertEqual(queue.last_max_active, 2)

    def test_missing_fenced_start_does_not_execute_pipeline(self):
        class Lost(LeasedJobs):
            def start(self, *_): return {}
        pipeline = FakePipeline(); worker = ResearchWorker(Lost([{"job_id": "one", "lease_token": "old"}]), pipeline)
        self.assertFalse(worker.process_one())
        self.assertFalse(hasattr(pipeline, "control_exists"))

    def test_cancelled_after_claim_does_not_execute_pipeline_and_completes_cancelled(self):
        class CancelledAfterClaim(LeasedJobs):
            def start(self, job_id, token):
                return {"job_id": job_id, "lease_token": token, "cancel_requested_at": "2026-07-28T12:00:00Z", "payload": {"limits": {}}}
        queue = CancelledAfterClaim([{"job_id": "one", "lease_token": "token-1"}])
        pipeline = FakePipeline()
        self.assertTrue(ResearchWorker(queue, pipeline).process_one())
        self.assertFalse(hasattr(pipeline, "control_exists"))
        self.assertEqual(queue.completed[0][2], "cancelled")


if __name__ == "__main__": unittest.main()
