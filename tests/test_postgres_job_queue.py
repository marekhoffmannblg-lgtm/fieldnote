from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))

from services.job_service import DuplicateActiveJobError, JobNotFoundError, JobService
import app as api


class Products:
    def product(self, slug):
        return {"product_id": "product:lionelo:amber:", "product_slug": slug, "brand": "Lionelo", "model": "Amber", "category_key": "strollers", "benchmark_group_key": "strollers-3w1"} if slug == "lionelo__amber" else {}


class Jobs:
    def __init__(self): self.values = []
    def create(self, value):
        if any(item["product_id"] == value["product_id"] and item.get("status", "queued") in {"queued", "leased", "running"} for item in self.values):
            from repositories.supabase_client import SupabaseRequestError
            raise SupabaseRequestError("research_jobs", 409)
        saved = {**value, "status": "queued"}; self.values.append(saved); return saved
    def get(self, job_id): return next((item for item in self.values if item["job_id"] == job_id), {})
    def list(self, **_): return list(self.values)
    def request_cancel(self, job_id):
        value = self.get(job_id); value["status"] = "cancelled"; return value
    def events(self, _): return []


class DurableQueueContractTests(unittest.TestCase):
    def test_schema_uses_atomic_claim_rpc_and_unique_active_product_index(self):
        sql = (ROOT / "supabase/migrations/202607280001_durable_research_queue.sql").read_text()
        baseline = (ROOT / "supabase/migrations/202607230004_jobs_audit.sql").read_text()
        self.assertIn("research_jobs_one_active_per_product", baseline)
        self.assertIn("for update skip locked", sql.lower())
        self.assertIn("pg_advisory_xact_lock", sql)
        self.assertIn("p_max_active", sql)
        self.assertIn("cancel_requested_at", sql)
        self.assertIn("lease_expires_at <= clock_timestamp()", sql)
        self.assertIn("lease_token = p_lease_token", sql)
        self.assertIn("grant execute on function public.fieldnote_claim_research_job", sql)

    def test_same_product_duplicate_is_rejected_but_missing_product_is_not_created(self):
        service = JobService(Jobs(), Products())
        first = service.enqueue(product_slug="lionelo__amber", requested_by="user-1")
        self.assertEqual(first["status"], "queued")
        with self.assertRaises(DuplicateActiveJobError): service.enqueue(product_slug="lionelo__amber", requested_by="user-2")
        with self.assertRaises(JobNotFoundError): service.enqueue(product_slug="missing__product", requested_by="user-1")

    def test_payload_contains_limits_and_selection_without_process_state(self):
        service = JobService(Jobs(), Products())
        job = service.enqueue(product_slug="lionelo__amber", requested_by="user-1", limits={"max_pages": 3, "max_ai_tokens": 4, "timeout_seconds": 5, "max_retries": 1}, selection={"selected_offer_ids": ["123"], "selected_manufacturer_source_ids": ["source-1"], "skip_ai": True})
        self.assertEqual(job["payload"]["limits"]["max_pages"], 3)
        self.assertEqual(job["payload"]["selection"]["selected_offer_ids"], ["123"])
        self.assertEqual(job["payload"]["selection"]["selected_manufacturer_source_ids"], ["source-1"])
        self.assertNotIn("child_pid", job["payload"])

    def test_terminal_job_can_retry_with_a_new_id_and_same_durable_payload(self):
        jobs = Jobs()
        service = JobService(jobs, Products())
        original = service.enqueue(product_slug="lionelo__amber", requested_by="user-1")
        original["status"] = "failed"
        retried = service.retry(original["job_id"], requested_by="user-2")
        self.assertNotEqual(retried["job_id"], original["job_id"])
        self.assertEqual(retried["payload"], original["payload"])
        self.assertEqual(retried["requested_by"], "user-2")

    def test_api_enqueues_and_returns_job_id_without_starting_a_process(self):
        service = JobService(Jobs(), Products())
        prior = getattr(api.app.state, "job_service", None)
        api.app.state.job_service = service
        try:
            response = TestClient(api.app).post("/api/jobs/research", json={"product_slug": "lionelo__amber"})
        finally:
            if prior is None: del api.app.state.job_service
            else: api.app.state.job_service = prior
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["job_id"])
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(response.json()["run_id"], response.json()["job_id"])
        self.assertEqual(response.json()["product_slug"], "lionelo__amber")


if __name__ == "__main__": unittest.main()
