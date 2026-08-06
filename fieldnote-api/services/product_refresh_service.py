"""Durable, single-product refresh orchestration.

The service is deliberately dependency-injected: production adapters can use
Supabase/Storage and Firecrawl, while CI uses deterministic fixtures.  A
refresh never reuses a discovery or scrape cache and only publishes after the
raw snapshot has been durably stored.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse
import ipaddress


class RefreshProvider(Protocol):
    def search(self, query: str, *, limit: int) -> Any: ...
    def scrape(self, url: str) -> Any: ...


class RefreshStorage(Protocol):
    def put(self, path: str, content: bytes, *, content_type: str) -> None: ...


class RefreshHistory(Protocol):
    def append_run(self, value: dict[str, Any]) -> dict[str, Any]: ...
    def append_source(self, value: dict[str, Any]) -> dict[str, Any]: ...


class RefreshError(RuntimeError):
    pass


@dataclass(frozen=True)
class RefreshLimits:
    max_pages: int = 10
    max_candidates: int = 20
    timeout_seconds: int = 900


@dataclass
class MemoryRefreshHistory:
    runs: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    run_sources: list[dict[str, Any]] = field(default_factory=list)

    def append_run(self, value: dict[str, Any]) -> dict[str, Any]:
        self.runs.append(dict(value))
        return value

    def append_source(self, value: dict[str, Any]) -> dict[str, Any]:
        key = (value.get("source_id"), value.get("content_hash"))
        for existing in self.sources:
            if (existing.get("source_id"), existing.get("content_hash")) == key:
                return {**existing, "_created": False}
        self.sources.append(dict(value))
        return {**value, "_created": True}

    def append_run_source(self, value: dict[str, Any]) -> dict[str, Any]:
        self.run_sources.append(dict(value))
        return value


@dataclass
class MemoryRefreshStorage:
    objects: dict[str, bytes] = field(default_factory=dict)

    def put(self, path: str, content: bytes, *, content_type: str) -> None:
        self.objects[path] = bytes(content)


def _body(response: Any) -> dict[str, Any]:
    # The shared client returns FirecrawlResponse, while fixture transports
    # commonly return the underlying dict. Support both without coupling the
    # service to a paid provider implementation.
    if hasattr(response, "data"):
        response = getattr(response, "data")
    if isinstance(response, dict):
        return response.get("data", response) if isinstance(response.get("data", response), dict) else {}
    return {}


def _items(response: Any) -> list[dict[str, Any]]:
    body = _body(response)
    value = body.get("items", body.get("results", []))
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _text(response: Any) -> str:
    body = _body(response)
    for key in ("markdown", "content", "html", "text"):
        if body.get(key):
            return str(body[key])
    return ""


def _canonical(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


@dataclass
class ProductRefreshService:
    provider: RefreshProvider
    storage: RefreshStorage
    history: RefreshHistory
    identity_gate: Any | None = None

    def refresh(self, *, product_id: str, product_slug: str, brand: str, model: str,
                configuration: str = "", limits: RefreshLimits | None = None) -> dict[str, Any]:
        limits = limits or RefreshLimits()
        run_id = str(uuid.uuid4())
        started = {"run_id": run_id, "product_id": product_id, "product_slug": product_slug,
                   "status": "running", "configuration": configuration, "sources": []}
        self.history.append_run(started)
        query = " ".join(part for part in (brand, model, configuration) if part).strip()
        try:
            # Explicitly omit cache/resume arguments: every invocation is fresh.
            search = self.provider.search(query, limit=limits.max_candidates)
            candidates = _items(search)[: limits.max_candidates]
            accepted = []
            rejected = []
            for item in candidates:
                url = str(item.get("url") or item.get("link") or "").strip()
                title = str(item.get("title") or item.get("name") or "")
                verdict = self._identity(title, brand, model, configuration, item)
                if verdict != "exact_match" or not url:
                    rejected.append({"url": url, "title": title, "reason": verdict})
                    continue
                accepted.append((url, title, item))
            if not accepted:
                return self._finish(started, "partial", {"reason": "no_exact_match", "rejected": rejected})

            fetched = []
            for url, title, item in accepted:
                # No cache/resume is passed to the provider; storage is written
                # before any semantic value can be committed.
                scraped = self.provider.scrape(url)
                text = _text(scraped)
                if not text:
                    continue
                source_id = str(item.get("source_id") or "").strip()
                if not source_id:
                    offer_id = str(item.get("offer_id") or "").strip()
                    source_id = f"allegro:{offer_id}" if offer_id else url
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                raw_hash = hashlib.sha256(json.dumps(scraped, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
                base = f"refresh/{product_id}/{source_id}/{content_hash}/{raw_hash}"
                raw_path, clean_path = f"{base}/raw.json", f"{base}/clean.txt"
                self.storage.put(raw_path, json.dumps(scraped, ensure_ascii=False, sort_keys=True, default=str).encode(), content_type="application/json")
                self.storage.put(clean_path, text.encode("utf-8"), content_type="text/plain")
                source = {"run_id": run_id, "product_id": product_id, "source_id": source_id,
                          "url": url, "title": title, "content_hash": content_hash,
                          "raw_object_path": raw_path, "clean_object_path": clean_path,
                          "status": "stored"}
                persisted = self.history.append_source(source)
                created = bool(persisted.pop("_created", True))
                run_source = {"run_id": run_id, "product_id": product_id,
                              "source_id": source_id, "content_hash": content_hash,
                              "raw_object_path": raw_path, "clean_object_path": clean_path}
                append_link = getattr(self.history, "append_run_source", None)
                if callable(append_link):
                    append_link(run_source)
                fetched.append({**persisted, "duplicate_snapshot": not created})
            if not fetched:
                return self._finish(started, "partial", {"reason": "no_content", "rejected": rejected})
            semantic_changed = any(not row["duplicate_snapshot"] for row in fetched)
            result = {"sources": fetched, "rejected": rejected, "semantic_snapshot_created": semantic_changed,
                      "last_known_good_preserved": False}
            return self._finish(started, "succeeded", result)
        except Exception as exc:
            return self._finish(started, "failed", {"error": str(exc), "last_known_good_preserved": True})

    def _identity(self, title: str, brand: str, model: str, configuration: str, item: dict[str, Any]) -> str:
        if self.identity_gate:
            return str(self.identity_gate(title=title, brand=brand, model=model, configuration=configuration, item=item))
        title_norm = _canonical(title)
        parsed = urlparse(str(item.get("url") or item.get("link") or ""))
        host = parsed.hostname or ""
        allowed = host == "allegro.pl" or host.endswith(".allegro.pl")
        try:
            private = bool(ipaddress.ip_address(host).is_private)
        except ValueError:
            private = False
        if parsed.scheme != "https" or not allowed or private:
            return "untrusted_url"
        if not all(token in title_norm for token in (_canonical(brand), _canonical(model)) if token):
            return "brand_or_model_mismatch"
        if configuration and _canonical(configuration) not in title_norm:
            return "configuration_mismatch"
        if any(word in title_norm for word in ("używany", "used", "akcesor", "adapter", "część")):
            return "rejected_non_product"
        return "exact_match"

    def _finish(self, run: dict[str, Any], status: str, result: dict[str, Any]) -> dict[str, Any]:
        run.update({"status": status, "result": result})
        self.history.append_run(run)
        return run
