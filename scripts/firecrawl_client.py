"""Small, injectable Firecrawl v2 client used by every external source.

The client deliberately contains no product-specific parsing.  It provides one
transport, retry and usage contract for search, scrape and crawl.  Tests inject
``transport`` and therefore never call the paid provider.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class FirecrawlError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, attempts: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts


@dataclass(frozen=True)
class FirecrawlUsage:
    credits_used: int | None = None
    pages: int = 0
    max_pages: int = 10
    usage_complete: bool = False


@dataclass(frozen=True)
class FirecrawlResponse:
    operation: str
    status_code: int
    data: dict[str, Any] = field(default_factory=dict)
    usage: FirecrawlUsage = field(default_factory=lambda: FirecrawlUsage())
    request_id: str = ""
    cached: bool = False
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300 and self.data.get("success", True) is not False


Transport = Callable[[str, str, dict[str, Any], float, Mapping[str, str]], tuple[int, dict[str, Any]]]


def _http_transport(url: str, method: str, payload: dict[str, Any], timeout: float, headers: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method=method, headers={**headers, "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return int(getattr(response, "status", 200)), json.loads(raw or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError:
            value = {"error": raw[:500]}
        return int(exc.code), value
    except URLError as exc:
        raise FirecrawlError(f"Firecrawl transport error: {type(exc.reason).__name__}") from exc


class FirecrawlClient:
    """Firecrawl v2 client with bounded retries and cache/resume semantics."""

    def __init__(self, *, api_key: str | None = None, base_url: str = "https://api.firecrawl.dev/v2", timeout: float = 30.0, max_retries: int = 2, backoff_seconds: float = 0.5, max_pages: int = 10, transport: Transport | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("FIRECRAWL_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = max(0.1, float(timeout))
        self.max_retries = max(0, min(int(max_retries), 5))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self.max_pages = max(1, min(int(max_pages), 100))
        self.transport = transport or _http_transport
        self.sleep = sleep

    def _request(self, operation: str, payload: dict[str, Any], *, cache: dict[str, Any] | None = None) -> FirecrawlResponse:
        if cache is not None:
            return FirecrawlResponse(operation, 200, dict(cache), FirecrawlUsage(pages=int(cache.get("pages", 0) or 0), max_pages=self.max_pages, usage_complete=True), cached=True)
        if not self.api_key:
            raise FirecrawlError("FIRECRAWL_API_KEY is required for live Firecrawl requests.")
        request_payload = dict(payload)
        request_payload.setdefault("limit", self.max_pages)
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        last_status: int | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                status, data = self.transport(f"{self.base_url}/{operation}", "POST", request_payload, self.timeout, headers)
            except FirecrawlError:
                if attempt > self.max_retries:
                    raise
                self.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
                continue
            last_status = status
            if status == 429 or status >= 500:
                if attempt <= self.max_retries:
                    self.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
                    continue
            if status < 200 or status >= 300 or data.get("success") is False:
                error = str(data.get("error") or data.get("message") or f"HTTP {status}")[:500]
                raise FirecrawlError(f"Firecrawl {operation} failed: {error}", status_code=status, attempts=attempt)
            raw_data = data.get("data") if isinstance(data.get("data"), dict) else data
            usage_raw = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            pages = raw_data.get("total", raw_data.get("pages", 0)) if isinstance(raw_data, dict) else 0
            usage = FirecrawlUsage(credits_used=_int_or_none(usage_raw.get("creditsUsed", usage_raw.get("credits_used"))), pages=_int(pages), max_pages=self.max_pages, usage_complete=bool(usage_raw or pages))
            return FirecrawlResponse(operation, status, raw_data if isinstance(raw_data, dict) else {"items": raw_data}, usage, str(data.get("id") or data.get("requestId") or ""), attempts=attempt)
        raise FirecrawlError(f"Firecrawl {operation} failed after retries", status_code=last_status, attempts=self.max_retries + 1)

    def search(self, query: str, *, limit: int | None = None, sources: list[str] | None = None, cache: dict[str, Any] | None = None) -> FirecrawlResponse:
        return self._request("search", {"query": str(query), "limit": max(1, min(int(limit or self.max_pages), self.max_pages)), **({"sources": sources} if sources else {})}, cache=cache)

    def scrape(self, url: str, *, formats: list[str] | None = None, only_main_content: bool = True, cache: dict[str, Any] | None = None) -> FirecrawlResponse:
        return self._request("scrape", {"url": str(url), "formats": formats or ["markdown"], "onlyMainContent": bool(only_main_content)}, cache=cache)

    def crawl(self, url: str, *, limit: int | None = None, include_paths: list[str] | None = None, cache: dict[str, Any] | None = None) -> FirecrawlResponse:
        return self._request("crawl", {"url": str(url), "limit": max(1, min(int(limit or self.max_pages), self.max_pages)), **({"includePaths": include_paths} if include_paths else {})}, cache=cache)


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    return _int(value) if value is not None else None
