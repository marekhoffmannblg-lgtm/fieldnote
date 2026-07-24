#!/usr/bin/env python3
"""Normalize classified stroller competitors without touching research artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path

from catalog_registry import PRODUCTS_PATH, atomic_write, load_products


STROLLER_GROUPS = {"light_stroller", "standard_stroller", "stroller_2in1", "stroller_3in1"}


def migrate(products: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    changed = 0
    normalized: list[dict[str, object]] = []
    for source in products:
        product = dict(source)
        if str(product.get("brand", "")).casefold() != "lionelo" and str(product.get("benchmark_group", "")) in STROLLER_GROUPS:
            target = {"category_key": "mobility", "subcategory_key": "strollers", "subcategory": "Wózki"}
            if any(product.get(key) != value for key, value in target.items()):
                product.update(target)
                changed += 1
        normalized.append(product)
    return normalized, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    products = load_products()
    migrated, changed = migrate(products)
    if not args.dry_run and changed:
        atomic_write(PRODUCTS_PATH, migrated)
    print(f"products_checked={len(products)}")
    print(f"competitors_migrated={changed}")
    print(f"written={'false' if args.dry_run else 'true'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
