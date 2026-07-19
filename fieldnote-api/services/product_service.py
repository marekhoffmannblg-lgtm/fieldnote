"""Product read service shared by product routes."""

from __future__ import annotations

from typing import Any

from repositories.snapshot_repository import SnapshotRepository


class ProductService:
    def __init__(self, snapshots: SnapshotRepository) -> None:
        self.snapshots = snapshots

    def list(self, limit: int, offset: int) -> dict[str, Any]:
        values = self.snapshots.catalog()
        page = values[offset:offset + limit]
        return {"schema_version": "1", "total": len(values), "limit": limit, "offset": offset, "items": page, "products": page}

    def detail(self, product_slug: str) -> dict[str, Any]:
        return self.snapshots.product(product_slug)
