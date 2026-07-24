from __future__ import annotations
from typing import Any
from repositories.supabase_client import SupabaseClient
class BenchmarkRepository:
    def __init__(self, client: SupabaseClient) -> None: self.client = client
    def upsert(self, value: dict[str, Any]) -> None: self.client.upsert("competitive_benchmarks", value, "benchmark_id")
