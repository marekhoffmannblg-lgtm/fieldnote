"""Read-only access to generated frontend snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


class SnapshotRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def catalog(self) -> list[dict[str, Any]]:
        value = read_json(self.root / "catalog.json", [])
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def product(self, product_slug: str) -> dict[str, Any]:
        value = read_json(self.root / "products" / f"{product_slug}.json", {})
        return value if isinstance(value, dict) else {}
