from __future__ import annotations
from typing import Any
from repositories.supabase_client import SupabaseClient


def brand_key(value: str) -> str:
    return "-".join(str(value).strip().casefold().split())


class CatalogRepository:
    def __init__(self, client: SupabaseClient) -> None: self.client = client
    def list_products(self) -> list[dict[str, Any]]:
        return self.client.select(
            "products",
            select="product_id,product_slug,group_key,brand,model,configuration,status,category_key,benchmark_group_key,created_at,updated_at,is_lionelo",
            order="brand.asc,model.asc",
        )
    def catalog(self) -> list[dict[str, Any]]:
        return [self._catalog_dto(row) for row in self.list_products()]

    @staticmethod
    def _catalog_dto(row: dict[str, Any]) -> dict[str, Any]:
        """Adapt lifecycle catalog rows to the frontend analysis contract."""
        updated_at = str(row.get("updated_at") or row.get("created_at") or "")
        return {
            "product_id": str(row.get("product_id") or ""),
            "brand": str(row.get("brand") or ""),
            "model": str(row.get("model") or ""),
            "configuration": str(row.get("configuration") or ""),
            "slug": str(row.get("product_slug") or ""),
            "scope": "catalog",
            "status": "refresh_recommended",
            "catalog_status": str(row.get("status") or "draft"),
            "status_reason": "no_research_completed",
            "status_updated_at": updated_at,
            "coverage": None,
            "fields_total": 0,
            "fields_completed": 0,
            "sources_count": 0,
            "source_counts": {"used_count": 0},
            "missing_fields_count": 0,
            "conflicts_count": 0,
            "updated_at": updated_at,
            "marketplaces": [],
            "category": "Bez kategorii",
            "category_key": str(row.get("category_key") or ""),
            "subcategory_key": "",
            "subcategory_label": "",
            "benchmark_group": "",
            "benchmark_group_key": str(row.get("benchmark_group_key") or ""),
            "benchmark_category": "Bez podkategorii",
        }
    def product(self, slug: str) -> dict[str, Any]:
        rows = self.client.select("products", select="*", product_slug=f"eq.{slug}")
        return rows[0] if rows else {}
    def upsert_brand(self, brand_key: str, display_name: str) -> str:
        rows = self.client.upsert("brands", {"brand_key": brand_key, "display_name": display_name}, "brand_key")
        return str(rows[0].get("id", "")) if rows else ""
    def upsert_product(self, product: dict[str, Any]) -> None:
        value = dict(product)
        key = brand_key(str(value.pop("brand_key", "") or value.get("brand", "")))
        brands = self.client.select("brands", select="id", brand_key=f"eq.{key}")
        if not brands or not brands[0].get("id"):
            raise ValueError("Product brand must exist before product upsert.")
        value["brand_id"] = brands[0]["id"]
        self.client.upsert("products", value, "product_id")
