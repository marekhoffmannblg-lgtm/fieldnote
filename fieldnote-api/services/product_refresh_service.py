"""Durable, single-product refresh orchestration.

The service is deliberately dependency-injected: production adapters can use
Supabase/Storage and Firecrawl, while CI uses deterministic fixtures.  A
refresh never reuses a discovery or scrape cache and only publishes after the
raw snapshot has been durably stored.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from urllib.parse import urlparse
import ipaddress
from urllib.request import Request, urlopen


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


class OpenAIRefreshExtractor:
    """Metered, schema-limited production fallback; never used by tests."""
    schema_version = "product-refresh-facts-v1"

    def __init__(self, api_key: str, *, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or os.getenv("FIELDNOTE_REFRESH_OPENAI_MODEL", "gpt-4.1-mini")

    @classmethod
    def from_env(cls) -> "OpenAIRefreshExtractor | None":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        return cls(key) if key else None

    def __call__(self, *, text: str, fields: list[str], max_tokens: int = 2000, timeout: float | None = None) -> dict[str, Any]:
        source_text = text[:16000]
        prompt = {"schema_version": self.schema_version, "fields": fields, "source_text": source_text, "rules": "Return only confirmed numeric kg values; do not infer."}
        prompt_text = json.dumps(prompt, ensure_ascii=False)
        estimated_prompt_tokens = max(1, (len(prompt_text) + 3) // 4)
        remaining_tokens = int(max_tokens) - estimated_prompt_tokens
        if remaining_tokens < 1:
            raise RefreshError("ai_budget_exceeded_before_request")
        body = {"model": self.model, "temperature": 0, "max_tokens": min(remaining_tokens, 8000), "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": "Extract only source-backed facts as JSON object {facts:{field:number}}."}, {"role": "user", "content": prompt_text}]}
        request = Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        with urlopen(request, timeout=max(0.1, float(timeout if timeout is not None else 120))) as response:
            raw = json.loads(response.read().decode())
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        value = json.loads(content) if isinstance(content, str) else {}
        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        total = usage.get("total_tokens")
        return {"facts": value.get("facts", value) if isinstance(value, dict) else {}, "usage": {"total_tokens": total, "complete": isinstance(total, int)}}


@dataclass(frozen=True)
class RefreshLimits:
    max_pages: int = 10
    max_candidates: int = 20
    timeout_seconds: int = 900
    max_ai_tokens: int = 20_000


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


def _provider_usage(response: Any) -> tuple[int | None, bool, bool]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, True, True
    credits = getattr(usage, "credits_used", None)
    complete = bool(getattr(usage, "usage_complete", False))
    return (int(credits) if isinstance(credits, int) else None), complete, isinstance(credits, int)


def _canonical(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


_FACT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("waga_wozka_kg", re.compile(r"(?:waga|weight)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*kg", re.I)),
    ("maksymalne_obciazenie_kg", re.compile(r"(?:maksymaln(?:e\s+)?obci[ąa]żenie|load capacity|max(?:imum)? load)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*kg", re.I)),
)


def _deterministic_facts(text: str, evidence: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Extract schema-named facts with field-level provenance.

    The compact rules are deliberately conservative.  Every unrecognised
    schema field is explicit so a later, injectable AI pass can work only on
    the unresolved set rather than inventing values from a whole document.
    """
    facts: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for field, pattern in _FACT_RULES:
        matches = pattern.findall(text)
        values = {str(match).replace(",", ".") for match in matches}
        if len(values) != 1:
            unresolved.append(field)
            continue
        value = float(next(iter(values)))
        facts[field] = value
        candidates.append({"field": field, "value": value, "evidence": evidence, "status": "deterministic"})
    return facts, candidates, unresolved


def _provider_call(method: Callable[..., Any], *args: Any, timeout: float, **kwargs: Any) -> Any:
    """Pass the remaining deadline to providers that support it.

    The production Firecrawl client aborts its underlying transport at that
    deadline. Fixture providers intentionally remain backward-compatible.
    """
    try:
        return method(*args, timeout=max(0.1, timeout), **kwargs)
    except TypeError as exc:
        if "timeout" not in str(exc):
            raise
        return method(*args, **kwargs)


def _ai_call(method: Callable[..., Any], *, text: str, fields: list[str], max_tokens: int, timeout: float) -> Any:
    try:
        return method(text=text, fields=fields, max_tokens=max_tokens, timeout=timeout)
    except TypeError as exc:
        if "timeout" not in str(exc):
            raise
        return method(text=text, fields=fields, max_tokens=max_tokens)


@dataclass
class ProductRefreshService:
    provider: RefreshProvider
    storage: RefreshStorage
    history: RefreshHistory
    identity_gate: Any | None = None
    ai_extractor: Callable[..., dict[str, Any]] | None = None

    def refresh(self, *, product_id: str, product_slug: str, brand: str, model: str,
                configuration: str = "", limits: RefreshLimits | None = None,
                cancel_check: Callable[[], bool] | None = None,
                benchmark_group: str = "") -> dict[str, Any]:
        limits = limits or RefreshLimits()
        run_id = str(uuid.uuid4())
        started = {"run_id": run_id, "product_id": product_id, "product_slug": product_slug,
                   "status": "running", "configuration": configuration, "sources": []}
        self.history.append_run(started)
        query = " ".join(part for part in (brand, model, configuration) if part).strip()
        deadline = time.monotonic() + max(0.01, float(limits.timeout_seconds))
        try:
            if cancel_check and cancel_check():
                return self._finish(started, "cancelled", {"reason": "cancel_requested", "last_known_good_preserved": True})
            # Explicitly omit cache/resume arguments: every invocation is fresh.
            candidate_limit = max(0, min(limits.max_candidates, limits.max_pages))
            search = _provider_call(self.provider.search, query, limit=candidate_limit, timeout=deadline - time.monotonic())
            candidates = _items(search)[:candidate_limit]
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
            all_facts: dict[str, Any] = {}
            field_candidates: list[dict[str, Any]] = []
            unresolved_fields: set[str] = set()
            fact_values: dict[str, list[Any]] = {}
            search_credits, provider_usage_complete, search_usage_known = _provider_usage(search)
            firecrawl_credits = search_credits or 0
            firecrawl_credits_known = search_usage_known
            for url, title, item in accepted:
                if cancel_check and cancel_check():
                    return self._finish(started, "cancelled", {"reason": "cancel_requested", "sources": fetched, "last_known_good_preserved": True})
                # No cache/resume is passed to the provider; storage is written
                # before any semantic value can be committed.
                scraped = _provider_call(self.provider.scrape, url, timeout=deadline - time.monotonic())
                scrape_credits, scrape_usage_complete, scrape_usage_known = _provider_usage(scraped)
                if scrape_credits is not None:
                    firecrawl_credits += scrape_credits
                else:
                    firecrawl_credits_known = firecrawl_credits_known and scrape_usage_known
                provider_usage_complete = provider_usage_complete and scrape_usage_complete
                if cancel_check and cancel_check():
                    return self._finish(started, "cancelled", {"reason": "cancel_requested", "sources": fetched, "last_known_good_preserved": True})
                text = _text(scraped)
                if not text:
                    continue
                offer_id = str(item.get("offer_id") or "").strip()
                source_id = f"allegro:{offer_id}" if offer_id else str(item.get("source_id") or "").strip() or url
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
                if persisted.get("id"):
                    run_source["snapshot_id"] = persisted["id"]
                append_link = getattr(self.history, "append_run_source", None)
                if callable(append_link):
                    append_link(run_source)
                evidence = {"source_id": source_id, "url": url, "content_hash": content_hash,
                            "excerpt": text[:1000], "snapshot_id": persisted.get("id")}
                facts, candidates, unresolved = _deterministic_facts(text, evidence)
                for field, value in facts.items():
                    fact_values.setdefault(field, []).append(value)
                field_candidates.extend(candidates)
                unresolved_fields.update(unresolved)
                fetched.append({**persisted, "duplicate_snapshot": not created, "evidence": evidence,
                                "candidates": candidates})
            if not fetched:
                return self._finish(started, "partial", {"reason": "no_content", "rejected": rejected})
            for field, values in fact_values.items():
                unique = {json.dumps(value, sort_keys=True, default=str) for value in values}
                if len(unique) == 1:
                    all_facts[field] = values[0]
                else:
                    unresolved_fields.add(field)
                    for candidate in field_candidates:
                        if candidate.get("field") == field:
                            candidate["status"] = "conflict"
            if cancel_check and cancel_check():
                return self._finish(started, "cancelled", {"reason": "cancel_requested", "sources": fetched, "last_known_good_preserved": True})
            semantic_changed = any(not row["duplicate_snapshot"] for row in fetched)
            group_key = "|".join(part for part in (_canonical(brand), _canonical(model)) if part)
            ai_state: dict[str, Any] = {"requested": False, "unresolved_fields": sorted(unresolved_fields)}
            # There is intentionally no default OpenAI client here: workers
            # provide a metered adapter in production, while fixtures inject a
            # deterministic function. The cap keeps a bad page bounded.
            if unresolved_fields and not self.ai_extractor:
                return self._finish(started, "partial", {"reason": "unresolved_fields_without_ai_adapter", "sources": fetched, "facts": all_facts, "candidates": field_candidates, "openai": ai_state, "no_mutation": True, "last_known_good_preserved": True})
            if unresolved_fields and self.ai_extractor:
                requested = sorted(unresolved_fields)[:3]
                ai_input = "\n".join(row["evidence"]["excerpt"] for row in fetched)
                estimated_input_tokens = max(1, (len(ai_input) + 3) // 4)
                remaining_ai_tokens = limits.max_ai_tokens - estimated_input_tokens
                if remaining_ai_tokens < 1:
                    return self._finish(started, "partial", {"reason": "ai_budget_exceeded_before_request", "sources": fetched, "facts": all_facts, "candidates": field_candidates, "openai": {"requested": False, "estimated_prompt_tokens": estimated_input_tokens}, "no_mutation": True, "last_known_good_preserved": True})
                try:
                    ai_values = _ai_call(self.ai_extractor, text=ai_input, fields=requested, max_tokens=remaining_ai_tokens, timeout=max(0.1, deadline - time.monotonic()))
                except Exception as exc:
                    return self._finish(started, "partial", {"reason": "ai_extractor_error", "error": str(exc), "sources": fetched, "facts": all_facts, "candidates": field_candidates, "openai": {"requested": True, "fields": requested, "error": type(exc).__name__}, "no_mutation": True, "last_known_good_preserved": True})
                ai_usage = ai_values.get("usage", {}) if isinstance(ai_values, dict) else {}
                values = ai_values.get("facts", ai_values) if isinstance(ai_values, dict) else {}
                if isinstance(values, dict):
                    for field in requested:
                        value = values.get(field)
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            all_facts[field] = float(value)
                            field_candidates.append({"field": field, "value": float(value), "evidence": [row["evidence"] for row in fetched], "status": "ai_fallback"})
                ai_state = {"requested": True, "unresolved_fields": requested, "resolved_fields": sorted(field for field in requested if field in all_facts)}
                if set(requested) - set(ai_state["resolved_fields"]) or not bool(ai_usage.get("complete", False)):
                    return self._finish(started, "partial", {"reason": "ai_response_incomplete", "sources": fetched, "facts": all_facts, "candidates": field_candidates, "openai": ai_state, "no_mutation": True, "last_known_good_preserved": True})
            if cancel_check and cancel_check():
                return self._finish(started, "cancelled", {"reason": "cancel_requested", "sources": fetched, "last_known_good_preserved": True})
            semantic_state = {"facts": all_facts, "evidence": [row["evidence"] for row in fetched],
                              "sources": [row.get("source_id", "") for row in fetched],
                              "candidates": field_candidates, "openai": ai_state}
            result = {"sources": fetched, "rejected": rejected, "semantic_snapshot_created": semantic_changed,
                      "usage": {"pages": len(fetched), "firecrawl_credits": firecrawl_credits, "firecrawl_credits_known": firecrawl_credits_known, "cost_used": float(firecrawl_credits) if firecrawl_credits_known else None, "ai_tokens": ai_usage.get("total_tokens") if unresolved_fields else 0, "usage_complete": provider_usage_complete and firecrawl_credits_known and (not unresolved_fields or bool(ai_usage.get("complete", False)))},
                      "usage_complete": provider_usage_complete and firecrawl_credits_known and (not unresolved_fields or bool(ai_usage.get("complete", False))),
                      "last_known_good_preserved": False,
                      "scoped_commit": {"scope": {"product_id": product_id, "group_key": group_key,
                                                    "benchmark_group": benchmark_group, "configuration": configuration,
                                                    "participant_product_ids": [product_id]},
                                        "semantic_state": semantic_state}}
            return self._finish(started, "succeeded", result)
        except TimeoutError as exc:
            return self._finish(started, "partial", {"error": str(exc), "reason": "provider_timeout", "last_known_good_preserved": True})
        except Exception as exc:
            if bool(getattr(exc, "timeout", False)):
                return self._finish(started, "partial", {"error": str(exc), "reason": "provider_timeout", "last_known_good_preserved": True})
            return self._finish(started, "failed", {"error": str(exc), "last_known_good_preserved": True})

    def _identity(self, title: str, brand: str, model: str, configuration: str, item: dict[str, Any]) -> str:
        parsed = urlparse(str(item.get("url") or item.get("link") or ""))
        host = parsed.hostname or ""
        allowed = host == "allegro.pl" or host.endswith(".allegro.pl")
        try:
            private = bool(ipaddress.ip_address(host).is_private)
        except ValueError:
            private = False
        if parsed.scheme != "https" or not allowed or private:
            return "untrusted_url"
        if self.identity_gate:
            return str(self.identity_gate(title=title, brand=brand, model=model, configuration=configuration, item=item))
        title_norm = _canonical(title)
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
