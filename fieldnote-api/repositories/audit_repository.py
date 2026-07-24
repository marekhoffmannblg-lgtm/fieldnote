from __future__ import annotations
from typing import Any
from repositories.supabase_client import SupabaseClient
class AuditRepository:
    def __init__(self, client: SupabaseClient) -> None: self.client = client
    def record(self, value: dict[str, Any]) -> None: self.client.request("POST", "audit_events", payload=value)
