from __future__ import annotations
from typing import Any
from repositories.supabase_client import SupabaseClient


def brand_key(value: str) -> str:
    return "-".join(str(value).strip().casefold().split())


class CatalogRepository:
    def __init__(self, client: SupabaseClient) -> None: self.client = client
    def list_products(self) -> list[dict[str, Any]]:
        return self.client.select("products", select="product_id,product_slug,group_key,brand,model,configuration,status,benchmark_group_key", order="brand.asc,model.asc")
    def catalog(self) -> list[dict[str, Any]]:
        return [{**row, "slug": row.get("product_slug", "")} for row in self.list_products()]
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
