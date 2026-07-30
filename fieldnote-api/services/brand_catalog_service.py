"""Brand catalog orchestration with an explicit preview/commit boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from discover_manufacturer_catalog import classify_catalog_record, discover_catalog, load_source_config  # noqa: E402


class BrandCatalogService:
    def __init__(self, *, config_path: Path | None = None, catalog_path: Path | None = None) -> None:
        self.config_path = config_path or PROJECT_ROOT / "config" / "sources" / "strollers.yaml"
        self.catalog_path = catalog_path or PROJECT_ROOT / "data" / "catalog" / "products.json"

    def configured_brands(self) -> list[dict[str, Any]]:
        config = load_source_config(self.config_path)
        sources = config.get("sources") if isinstance(config.get("sources"), list) else []
        return [dict(item) for item in sources if isinstance(item, dict) and item.get("brand")]

    def current(self, brand: str | None = None) -> dict[str, Any]:
        try:
            value = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = []
        records = value.get("products", []) if isinstance(value, dict) else value
        records = [classify_catalog_record(item) for item in records if isinstance(item, dict)] if isinstance(records, list) else []
        if brand:
            records = [item for item in records if str(item.get("brand", "")).casefold() == brand.casefold()]
        return {"schema_version": "1", "source": "tracked_catalog", "brand": brand, "items": records, "counts": {"total": len(records), "excluded": sum(item.get("catalog_status") == "excluded" for item in records), "review_required": sum(item.get("catalog_status") == "review_required" for item in records), "unclassified_real_products": 0}}

    def discover(self, brand: str, *, fixture_root: Path | None = None, client: Any = None, category_url: str | None = None) -> dict[str, Any]:
        return discover_catalog(brand=brand, fixture_root=fixture_root, client=client, category_url=category_url)
