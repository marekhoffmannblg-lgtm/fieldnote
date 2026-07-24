"""Persistent, dependency-free product catalogue shared by the local pipeline.

The catalogue registers a research target before fetched sources are grouped.
It deliberately stores product identity separately from data extracted from a
marketplace page, which can contain an incorrect brand in a noisy heading.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark_taxonomy import CATEGORY, TAXONOMY_VERSION
from category_registry import assignment_from_legacy, category_status, validate_category_assignment
from p0_runtime import atomic_write_json


ROOT = Path(__file__).resolve().parent.parent
CATALOG_ROOT = ROOT / "data" / "catalog"
BRANDS_PATH = CATALOG_ROOT / "brands.json"
CATEGORIES_PATH = CATALOG_ROOT / "categories.json"
PRODUCTS_PATH = CATALOG_ROOT / "products.json"
DEFAULT_CATEGORY = CATEGORY
DEFAULT_BENCHMARK_CATEGORY = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.replace("ł", "l").replace("Ł", "L").lower()).strip()


def slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalized(value)).strip("-") or "unknown"


def group_key_for(brand: object, model: object, configuration: object = "") -> str:
    base = f"{normalized(brand)}|{normalized(model)}"
    return f"{base}|{normalized(configuration)}" if normalized(configuration) else base


def product_slug_for(brand: object, model: object, configuration: object = "") -> str:
    base = f"{slug(brand)}__{slug(model)}"
    return f"{base}-{slug(configuration)}" if normalized(configuration) else base


def read_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def atomic_write(path: Path, value: object) -> None:
    atomic_write_json(path, value)


def load_products() -> list[dict[str, Any]]:
    products, _changed = migrate_product_category_fields(read_list(PRODUCTS_PATH))
    return products


def migrate_product_category_fields(products: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Add canonical keys without rewriting legacy labels or guessing 2w1/3w1."""
    changed = False
    migrated: list[dict[str, Any]] = []
    for original in products:
        product = dict(original)
        if not str(product.get("category_key", "")).strip():
            assignment = assignment_from_legacy(product.get("category"), product.get("benchmark_category"))
            product["category_key"] = assignment["category_key"]
            product["benchmark_group"] = assignment["benchmark_group"]
            product["category_classification_status"] = category_status(product)
            changed = True
        elif "benchmark_group" not in product:
            product["benchmark_group"] = ""
            product["category_classification_status"] = category_status(product)
            changed = True
        elif "category_classification_status" not in product:
            product["category_classification_status"] = category_status(product)
            changed = True
        migrated.append(product)
    return migrated, changed


def migrate_catalog_categories() -> int:
    products, changed = migrate_product_category_fields(read_list(PRODUCTS_PATH))
    if changed:
        atomic_write(PRODUCTS_PATH, products)
    return sum(1 for product in products if product.get("category_key"))


def product_for_group_key(group_key: str) -> dict[str, Any]:
    target = str(group_key or "").strip()
    for product in load_products():
        if str(product.get("group_key", "")).strip() == target:
            return product
    return {}


def ensure_catalog_product(
    brand: str,
    model: str,
    *,
    category: str = DEFAULT_CATEGORY,
    subcategory: str = "",
    subcategory_key: str = "",
    benchmark_category: str = DEFAULT_BENCHMARK_CATEGORY,
    taxonomy_status: str = "review_required",
    status: str = "waiting_for_analysis",
    category_key: str = "",
    benchmark_group: str = "",
    configuration: str = "",
    scope: str = "test",
) -> dict[str, Any]:
    """Create or return a product identity without deriving it from page text."""
    brand = " ".join(str(brand or "").split()).strip()
    model = " ".join(str(model or "").split()).strip()
    configuration = " ".join(str(configuration or "").split()).strip()
    if not brand or not model:
        raise ValueError("Katalog produktu wymaga marki i modelu.")

    group_key = group_key_for(brand, model, configuration)
    products = load_products()
    existing = next((item for item in products if item.get("group_key") == group_key), None)
    if existing:
        return existing

    assignment = (
        validate_category_assignment(category_key, benchmark_group)
        if category_key or benchmark_group
        else assignment_from_legacy(category, benchmark_category)
    )

    product = {
        "product_id": f"product:{slug(brand)}:{slug(model)}:{slug(configuration)}",
        "brand": brand,
        "brand_slug": slug(brand),
        "category": category,
        "category_slug": slug(category),
        "subcategory": subcategory,
        "subcategory_key": subcategory_key,
        "benchmark_category": benchmark_category,
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_status": taxonomy_status,
        "category_key": assignment["category_key"],
        "benchmark_group": assignment["benchmark_group"],
        "benchmark_group_key": assignment["benchmark_group"],
        "category_classification_status": "classified" if assignment["benchmark_group"] else "requires_classification",
        "model": model,
        "model_slug": slug(model),
        "configuration": configuration,
        "group_key": group_key,
        "status": status,
        "scope": scope,
        "created_at": utc_now(),
    }
    products.append(product)
    products.sort(key=lambda item: (str(item.get("brand", "")).lower(), str(item.get("model", "")).lower()))
    atomic_write(PRODUCTS_PATH, products)

    brands = read_list(BRANDS_PATH)
    if not any(item.get("brand_slug") == product["brand_slug"] for item in brands):
        brands.append({"brand": brand, "brand_slug": product["brand_slug"], "created_at": product["created_at"]})
        brands.sort(key=lambda item: str(item.get("brand", "")).lower())
        atomic_write(BRANDS_PATH, brands)

    categories = read_list(CATEGORIES_PATH)
    category_key = f"{product['category_slug']}|{slug(benchmark_category)}"
    if not any(f"{item.get('category_slug', '')}|{slug(item.get('benchmark_category', ''))}" == category_key for item in categories):
        categories.append(
            {
                "category": category,
                "category_slug": product["category_slug"],
                "subcategory": subcategory,
                "benchmark_category": benchmark_category,
                "taxonomy_version": TAXONOMY_VERSION,
                "taxonomy_status": taxonomy_status,
                "created_at": product["created_at"],
            }
        )
        categories.sort(key=lambda item: (str(item.get("category", "")).lower(), str(item.get("benchmark_category", "")).lower()))
        atomic_write(CATEGORIES_PATH, categories)
    return product


def ensure_group_directory(product: dict[str, Any]) -> Path:
    """Reserve only the canonical group directory; do not write a fake group.json."""
    directory = ROOT / "output" / "model_groups" / f"{product['brand_slug']}__{product['model_slug']}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory
