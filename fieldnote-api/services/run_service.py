"""Run list projection without process execution side effects."""

from __future__ import annotations

from typing import Any, Callable

from services.source_service import paginate


def index_runs(manifests: list[dict[str, Any]], index_record: Callable[[dict[str, Any]], dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    ordered = sorted(manifests, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return paginate([index_record(item) for item in ordered], limit, offset)
