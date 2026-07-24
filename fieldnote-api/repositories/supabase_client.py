"""Small injectable PostgREST client; server credentials never reach the UI."""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SupabaseConfigurationError(RuntimeError):
    pass


class SupabaseClient:
    def __init__(self, url: str, service_key: str) -> None:
        if not url or not service_key:
            raise SupabaseConfigurationError("Supabase server configuration is required.")
        self.url, self.service_key = url.rstrip("/"), service_key

    @classmethod
    def from_env(cls) -> "SupabaseClient":
        return cls(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))

    def request(self, method: str, table: str, *, query: dict[str, str] | None = None, payload: Any = None) -> list[dict[str, Any]]:
        suffix = f"?{urlencode(query)}" if query else ""
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            f"{self.url}/rest/v1/{table}{suffix}", data=body, method=method,
            headers={"apikey": self.service_key, "Authorization": f"Bearer {self.service_key}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=representation"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                value = json.loads(response.read().decode() or "[]")
        except HTTPError as error:
            raise RuntimeError(f"Supabase {table} request failed: {error.code}") from error
        return value if isinstance(value, list) else []

    def select(self, table: str, **query: str) -> list[dict[str, Any]]:
        return self.request("GET", table, query=query)

    def upsert(self, table: str, payload: dict[str, Any], conflict: str) -> list[dict[str, Any]]:
        return self.request("POST", table, query={"on_conflict": conflict}, payload=payload)

    def auth_admin(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(f"{self.url}/auth/v1/admin/{path.lstrip('/')}", data=body, method=method, headers={"apikey": self.service_key, "Authorization": f"Bearer {self.service_key}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=10) as response: value = json.loads(response.read().decode() or "{}")
        except HTTPError as error: raise RuntimeError(f"Supabase Auth admin request failed: {error.code}") from error
        return value if isinstance(value, dict) else {}
