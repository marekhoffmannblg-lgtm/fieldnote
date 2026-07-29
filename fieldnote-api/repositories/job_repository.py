from __future__ import annotations

from typing import Any

from repositories.supabase_client import SupabaseClient


class JobRepository:
    """Persistence-only queue adapter. Claim correctness lives in SQL RPCs."""

    def __init__(self, client: SupabaseClient) -> None:
        self.client = client

    def create(self, value: dict[str, Any]) -> dict[str, Any]:
        rows = self.client.request("POST", "research_jobs", payload=value)
        return rows[0] if rows else {}

    # Kept for the Unit 3 repository contract.
    def upsert(self, value: dict[str, Any]) -> None:
        self.client.upsert("research_jobs", value, "job_id")

    def get(self, job_id: str) -> dict[str, Any]:
        rows = self.client.select("research_jobs", select="*", job_id=f"eq.{job_id}")
        return rows[0] if rows else {}

    def list(self, *, product_id: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        query = {"select": "*", "order": "requested_at.desc", "limit": str(limit), "offset": str(offset)}
        if product_id:
            query["product_id"] = f"eq.{product_id}"
        return self.client.select("research_jobs", **query)

    def count(self, *, product_id: str | None = None) -> int:
        """Return the durable total without applying the list page limit."""
        payload = {"p_product_id": product_id} if product_id else {}
        rows = self.client.rpc("fieldnote_count_research_jobs", payload)
        if not rows:
            return 0
        value = rows[0]
        raw = value.get("count", value.get("fieldnote_count_research_jobs", 0)) if isinstance(value, dict) else 0
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0

    def claim(self, worker_id: str, lease_seconds: int, max_active: int = 2) -> dict[str, Any]:
        rows = self.client.rpc("fieldnote_claim_research_job", {"p_worker_id": worker_id, "p_lease_seconds": lease_seconds, "p_max_active": max_active})
        return rows[0] if rows else {}

    def start(self, job_id: str, lease_token: str) -> dict[str, Any]:
        rows = self.client.rpc("fieldnote_start_research_job", {"p_job_id": job_id, "p_lease_token": lease_token})
        return rows[0] if rows else {}

    def heartbeat(self, job_id: str, lease_token: str, lease_seconds: int) -> dict[str, Any]:
        rows = self.client.rpc("fieldnote_heartbeat_research_job", {"p_job_id": job_id, "p_lease_token": lease_token, "p_lease_seconds": lease_seconds})
        return rows[0] if rows else {}

    def complete(self, job_id: str, lease_token: str, status: str, result: dict[str, Any], usage: dict[str, Any], cost_used: float) -> dict[str, Any]:
        rows = self.client.rpc("fieldnote_complete_research_job", {"p_job_id": job_id, "p_lease_token": lease_token, "p_status": status, "p_result": result, "p_usage": usage, "p_cost_used": cost_used})
        return rows[0] if rows else {}

    def complete_incremental(self, job_id: str, lease_token: str, status: str, result: dict[str, Any], usage: dict[str, Any], cost_used: float, scope: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
        rows = self.client.rpc("fieldnote_commit_incremental_research_job", {
            "p_job_id": job_id, "p_lease_token": lease_token, "p_status": status,
            "p_result": result, "p_usage": usage, "p_cost_used": cost_used,
            "p_scope": scope, "p_snapshots": snapshots,
        })
        return rows[0] if rows else {}

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        rows = self.client.rpc("fieldnote_request_research_job_cancel", {"p_job_id": job_id})
        return rows[0] if rows else {}

    def events(self, job_id: str) -> list[dict[str, Any]]:
        # events.job_id is the internal UUID FK, while the API exposes the
        # public text job_id. Resolve the UUID before querying to preserve the
        # durable event history in job detail responses.
        job = self.get(job_id)
        internal_id = str(job.get("id", "")).strip()
        if not internal_id:
            return []
        return self.client.select("research_job_events", select="*", job_id=f"eq.{internal_id}", order="created_at.asc")
