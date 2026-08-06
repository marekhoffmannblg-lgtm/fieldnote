from __future__ import annotations

import hashlib
import json
from typing import Any

from repositories.supabase_client import SupabaseClient


class SupabaseRefreshStorage:
    def __init__(self, client: SupabaseClient) -> None:
        self.client = client

    def put(self, path: str, content: bytes, *, content_type: str) -> None:
        bucket = "source-clean" if content_type == "text/plain" else "source-raw"
        self.client.storage_upload(bucket, path, content, content_type=content_type)


class SupabaseRefreshHistory:
    """Persistence adapter; source/snapshot/link writes are explicit and FK-safe."""
    def __init__(self, client: SupabaseClient) -> None:
        self.client = client

    def append_run(self, value: dict[str, Any]) -> dict[str, Any]:
        payload = {"run_id": value["run_id"], "product_id": value["product_id"], "configuration": value.get("configuration", ""), "status": value.get("status", "running"), "result": value.get("result", {})}
        rows = self.client.upsert("product_refresh_runs", payload, "run_id")
        return rows[0] if rows else payload

    def append_source(self, value: dict[str, Any]) -> dict[str, Any]:
        source_id = str(value["source_id"])
        source = {"source_id": source_id, "source_type": "marketplace_offer", "marketplace": "allegro", "offer_id": source_id.removeprefix("allegro:"), "canonical_url": value["url"], "original_url": value["url"], "domain": "allegro.pl", "content_hash": value["content_hash"]}
        self.client.upsert("sources", source, "source_id")
        link_id = f"{value['product_id']}:{source_id}"
        self.client.upsert("product_source_links", {"link_id": link_id, "product_id": value["product_id"], "source_id": source_id, "group_key": "", "role": "refresh"}, "link_id")
        existing = self.client.select("product_refresh_snapshots", select="*", source_id=f"eq.{source_id}", content_hash=f"eq.{value['content_hash']}")
        if existing:
            return {**existing[0], "_created": False}
        payload = {"product_id": value["product_id"], "source_id": source_id, "canonical_url": value["url"], "content_hash": value["content_hash"], "raw_object_path": value["raw_object_path"], "clean_object_path": value["clean_object_path"]}
        rows = self.client.request("POST", "product_refresh_snapshots", payload=payload)
        row = rows[0] if rows else payload
        return {**row, "_created": True}

    def append_run_source(self, value: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.client.select("product_refresh_snapshots", select="id", source_id=f"eq.{value['source_id']}", content_hash=f"eq.{value['content_hash']}")
        if not snapshot:
            raise RuntimeError("refresh snapshot missing before run-source link")
        payload = {"run_id": value["run_id"], "snapshot_id": snapshot[0]["id"], "product_id": value["product_id"], "raw_object_path": value["raw_object_path"], "clean_object_path": value["clean_object_path"]}
        rows = self.client.request("POST", "product_refresh_run_sources", payload=payload)
        return rows[0] if rows else payload
