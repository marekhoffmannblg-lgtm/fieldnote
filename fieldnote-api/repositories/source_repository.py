from __future__ import annotations
from typing import Any
from repositories.supabase_client import SupabaseClient


class SourceRepository:
    def __init__(self, client: SupabaseClient) -> None: self.client = client
    def upsert_source(self, value: dict[str, Any]) -> None: self.client.upsert("sources", value, "source_id")
    def upsert_link(self, value: dict[str, Any]) -> None: self.client.upsert("product_source_links", value, "link_id")
    def upsert_evidence(self, value: dict[str, Any]) -> None: self.client.upsert("evidence_items", value, "evidence_id")
