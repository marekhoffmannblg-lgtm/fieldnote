"""Business rules for durable research jobs; database remains the queue."""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from repositories.job_repository import JobRepository
from repositories.supabase_client import SupabaseRequestError


class ProductLookup(Protocol):
    def product(self, slug: str) -> dict[str, Any]: ...


class DuplicateActiveJobError(RuntimeError):
    pass


class JobNotFoundError(RuntimeError):
    pass


class JobNotRetryableError(RuntimeError):
    pass


def _positive_int(value: Any, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def normalized_limits(value: dict[str, Any] | None) -> dict[str, int]:
    raw = value or {}
    return {
        "max_pages": _positive_int(raw.get("max_pages"), default=10, maximum=100),
        "max_ai_tokens": _positive_int(raw.get("max_ai_tokens"), default=20_000, maximum=2_000_000),
        "timeout_seconds": _positive_int(raw.get("timeout_seconds"), default=900, maximum=7_200),
        "max_retries": _positive_int(raw.get("max_retries"), default=1, maximum=5),
    }


def cost_number(value: Any) -> float:
    try:
        return float(max(Decimal("0"), Decimal(str(value))))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


class JobService:
    def __init__(self, jobs: JobRepository, products: ProductLookup) -> None:
        self.jobs, self.products = jobs, products

    def enqueue(self, *, product_slug: str, requested_by: str, limits: dict[str, Any] | None = None, selection: dict[str, Any] | None = None, cost_limit: float | None = None, job_type: str = "research") -> dict[str, Any]:
        product = self.products.product(product_slug)
        product_id = str(product.get("product_id", "")).strip()
        if not product_id:
            raise JobNotFoundError(product_slug)
        value = {
            "job_id": str(uuid.uuid4()),
            "product_id": product_id,
            "requested_by": requested_by,
            "cost_limit": cost_number(cost_limit) if cost_limit is not None else None,
            "payload": {
                "schema_version": "1",
                "job_type": job_type if job_type in {"research", "product_refresh"} else "research",
                "product_slug": product_slug,
                "brand": str(product.get("brand", "")),
                "model": str(product.get("model", "")),
                "configuration": str(product.get("configuration", "")),
                "category_key": str(product.get("category_key", "")),
                "benchmark_group": str(product.get("benchmark_group_key", product.get("benchmark_group", ""))),
                "limits": normalized_limits(limits),
                "selection": selection or {},
            },
        }
        try:
            result = self.jobs.create(value)
        except SupabaseRequestError as exc:
            if exc.status_code == 409:
                raise DuplicateActiveJobError(product_slug) from exc
            raise
        return result or {**value, "status": "queued"}

    def get(self, job_id: str) -> dict[str, Any]:
        value = self.jobs.get(job_id)
        if not value:
            raise JobNotFoundError(job_id)
        return value

    def list(self, *, product_id: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return self.jobs.list(product_id=product_id, limit=min(max(limit, 1), 200), offset=max(offset, 0))

    def count(self, *, product_id: str | None = None) -> int:
        counter = getattr(self.jobs, "count", None)
        if callable(counter):
            return max(0, int(counter(product_id=product_id)))
        # Compatibility for isolated legacy fakes. The durable repository
        # always takes the RPC path above, so production totals are unpaged.
        return len(self.jobs.list(product_id=product_id, limit=200, offset=0))

    def cancel(self, job_id: str) -> dict[str, Any]:
        value = self.jobs.request_cancel(job_id)
        if not value:
            raise JobNotFoundError(job_id)
        return value

    def retry(self, job_id: str, *, requested_by: str) -> dict[str, Any]:
        previous = self.get(job_id)
        if str(previous.get("status", "")) not in {"failed", "partial", "cancelled"}:
            raise JobNotRetryableError(job_id)
        value = {
            "job_id": str(uuid.uuid4()),
            "product_id": str(previous.get("product_id", "")),
            "requested_by": requested_by,
            "cost_limit": previous.get("cost_limit"),
            "payload": previous.get("payload") if isinstance(previous.get("payload"), dict) else {},
        }
        if not value["product_id"] or not value["payload"]:
            raise JobNotRetryableError(job_id)
        try:
            result = self.jobs.create(value)
        except SupabaseRequestError as exc:
            if exc.status_code == 409:
                raise DuplicateActiveJobError(job_id) from exc
            raise
        return result or {**value, "status": "queued"}

    def detail(self, job_id: str) -> dict[str, Any]:
        value = self.get(job_id)
        return {**value, "events": self.jobs.events(job_id)}
