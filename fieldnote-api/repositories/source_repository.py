from __future__ import annotations
from typing import Any
from repositories.supabase_client import SupabaseClient


class SourceRepository:
    def __init__(self, client: SupabaseClient) -> None: self.client = client
    def upsert_source(self, value: dict[str, Any]) -> None: self.client.upsert("sources", {key: value.get(key) for key in ("source_id", "source_type", "marketplace", "offer_id", "canonical_url", "original_url", "domain", "content_hash") if key in value}, "source_id")
    def upsert_link(self, value: dict[str, Any]) -> None: self.client.upsert("product_source_links", {key: value.get(key) for key in ("link_id", "product_id", "source_id", "group_key", "role") if key in value}, "link_id")
    def upsert_evidence(self, value: dict[str, Any]) -> None: self.client.upsert("evidence_items", {key: value.get(key) for key in ("evidence_id", "product_id", "source_id", "product_source_link_id", "field_name", "normalized_field_name", "value", "normalized_value", "excerpt", "evidence_status", "validation_status", "confidence") if key in value}, "evidence_id")
