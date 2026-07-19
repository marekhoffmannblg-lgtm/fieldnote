"""Offline P1 taxonomy migration for the persisted FIELDNOTE catalogue."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark_taxonomy import TAXONOMY_VERSION, classify_from_texts
from p0_runtime import atomic_write_json


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "catalog"
PRODUCTS_PATH = CATALOG / "products.json"
CATEGORIES_PATH = CATALOG / "categories.json"
GROUPS = ROOT / "output" / "model_groups"
REGISTRY = ROOT / "output" / "source_registry.jsonl"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [] if path.name.endswith("s.json") else {}


def registry_by_group() -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    try:
        lines = REGISTRY.read_text(encoding="utf-8").splitlines()
    except OSError:
        return indexed
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("group_key"):
            indexed.setdefault(str(item["group_key"]), []).append(item)
    return indexed


def source_texts(product: dict[str, Any], sources: list[dict[str, Any]]) -> list[str]:
    # Marketplace titles are the stable product-local context.  Full listing
    # descriptions can include related products, bundles and recommendations;
    # use a local description only when the source has no title at all.
    texts = [str(source.get("title", "")) for source in sources if str(source.get("title", "")).strip()]
    for source in sources:
        if str(source.get("title", "")).strip():
            continue
        raw = str(source.get("content_path", "") or "").strip()
        if not raw:
            continue
        path = ROOT / raw
        try:
            # A short local description is sufficient for taxonomy signals and
            # avoids using a model name by itself as the classifier input.
            texts.append(path.read_text(encoding="utf-8", errors="replace")[:12_000])
        except OSError:
            continue
    return texts


def main() -> int:
    products = read_json(PRODUCTS_PATH)
    if not isinstance(products, list):
        print("Brak data/catalog/products.json")
        return 1
    indexed = registry_by_group()
    categories: dict[tuple[str, str, str], dict[str, str]] = {}
    migrated = review_required = 0
    for product in products:
        if not isinstance(product, dict):
            continue
        group_key = str(product.get("group_key", ""))
        taxonomy = classify_from_texts(source_texts(product, indexed.get(group_key, [])))
        product.update(taxonomy)
        product["category_slug"] = "wozki-dzieciece"
        migrated += 1
        if taxonomy["taxonomy_status"] != "classified":
            review_required += 1
        categories[(taxonomy["category"], taxonomy["subcategory"], taxonomy["benchmark_category"])] = {
            "category": taxonomy["category"],
            "category_slug": "wozki-dzieciece",
            "subcategory": taxonomy["subcategory"],
            "benchmark_category": taxonomy["benchmark_category"],
            "taxonomy_version": TAXONOMY_VERSION,
            "taxonomy_status": taxonomy["taxonomy_status"],
        }
        group_path = GROUPS / f"{product.get('brand_slug', '')}__{product.get('model_slug', '')}" / "group.json"
        group = read_json(group_path)
        if isinstance(group, dict) and group.get("group_key") == group_key:
            group.update(taxonomy)
            atomic_write_json(group_path, group)

    atomic_write_json(PRODUCTS_PATH, products)
    atomic_write_json(CATEGORIES_PATH, sorted(categories.values(), key=lambda item: (item["category"], item["subcategory"])))
    print(f"taxonomy_migrated_products={migrated}")
    print(f"taxonomy_review_required={review_required}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
