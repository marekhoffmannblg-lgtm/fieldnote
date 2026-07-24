from __future__ import annotations
from typing import Any
from repositories.supabase_client import SupabaseClient
class JobRepository:
    def __init__(self, client: SupabaseClient) -> None: self.client = client
    def upsert(self, value: dict[str, Any]) -> None: self.client.upsert("research_jobs", value, "job_id")
