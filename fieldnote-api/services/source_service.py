"""Read-only source list helpers shared by API routes."""

from __future__ import annotations

from typing import Any

from repositories.source_repository import SourceRepository


def paginate(items: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    safe_limit = min(max(int(limit), 1), 500)
    safe_offset = max(int(offset), 0)
    page = items[safe_offset:safe_offset + safe_limit]
    return {"schema_version": "1", "total": len(items), "limit": safe_limit, "offset": safe_offset, "items": page}
