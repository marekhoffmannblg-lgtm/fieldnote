#!/usr/bin/env python3
"""Import approved Lionelo stroller rows into the canonical FIELDNOTE catalog.

This importer never starts research. It only creates catalogue identities from
the generated taxonomy and is safe to run repeatedly.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from catalog_registry import ensure_catalog_product, group_key_for, load_products  # noqa: E402


TAXONOMY = ROOT / "output" / "taxonomy"


def registry_labels(path: Path) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    categories: dict[str, str] = {}
    subcategories: dict[str, str] = {}
    groups: dict[str, str] = {}
    for category in payload.get("categories", []):
        categories[str(category["key"])] = str(category["label_pl"])
        for subcategory in category.get("subcategories", []):
            subcategories[str(subcategory["key"])] = str(subcategory["label_pl"])
            for group in subcategory.get("benchmark_groups", []):
                groups[str(group["key"])] = str(group["label_pl"])
    return categories, subcategories, groups


def matching_rows(inventory: Path) -> list[dict[str, str]]:
    with inventory.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        row for row in rows
        if row.get("brand") == "Lionelo"
        and row.get("category_key") == "mobility"
        and row.get("subcategory_key") == "strollers"
        and row.get("benchmarkable") == "yes"
    ]


def import_rows(rows: list[dict[str, str]], labels: tuple[dict[str, str], dict[str, str], dict[str, str]], *, dry_run: bool = False) -> Counter[str]:
    """Import rows using the canonical catalogue writer and return outcomes."""
    category_labels, subcategory_labels, group_labels = labels
    outcomes: Counter[str] = Counter()
    existing_by_identity = {str(item.get("group_key", "")): item for item in load_products()}
    for row in rows:
        brand = row["brand"].strip()
        model = row["model"].strip()
        configuration = row.get("configuration", "").strip()
        category_key = row["category_key"]
        subcategory_key = row["subcategory_key"]
        benchmark_group = row["benchmark_group_key"]
        identity = group_key_for(brand, model, configuration)
        if not all((brand, model, category_key, subcategory_key, benchmark_group)):
            outcomes["ERROR"] += 1
            print(f"ERROR {identity}: incomplete taxonomy row")
            continue
        existing = existing_by_identity.get(identity)
        if existing:
            same = (
                str(existing.get("category_key", "")) == category_key
                and str(existing.get("subcategory_key", "")) == subcategory_key
                and str(existing.get("benchmark_group_key", existing.get("benchmark_group", ""))) == benchmark_group
                and str(existing.get("configuration", "")) == configuration
            )
            outcomes["SKIP" if same else "CONFLICT"] += 1
            print(f"{'SKIP' if same else 'CONFLICT'} {identity}" + ("" if same else ": existing taxonomy differs"))
            continue
        outcomes["CREATE"] += 1
        print(f"CREATE {identity}")
        if dry_run:
            continue
        product = ensure_catalog_product(
            brand, model, category=category_labels[category_key], subcategory=subcategory_labels[subcategory_key],
            benchmark_category=group_labels[benchmark_group], taxonomy_status="classified", status="refresh_recommended",
            category_key=category_key, subcategory_key=subcategory_key, benchmark_group=benchmark_group,
            configuration=configuration, scope="production",
        )
        existing_by_identity[identity] = product
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=TAXONOMY / "FIELDNOTE_product_inventory_classified.csv")
    parser.add_argument("--registry", type=Path, default=TAXONOMY / "category_registry.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = matching_rows(args.inventory)
    outcomes = import_rows(rows, registry_labels(args.registry), dry_run=args.dry_run)

    print(f"selected={len(rows)}")
    for outcome in ("CREATE", "SKIP", "CONFLICT", "ERROR"):
        print(f"{outcome.lower()}={outcomes[outcome]}")
    expected = Counter({"light_stroller": 10, "standard_stroller": 7, "stroller_2in1": 8, "stroller_3in1": 9})
    actual = Counter(row["benchmark_group_key"] for row in rows)
    if len(rows) != 34 or actual != expected:
        print("ERROR inventory does not match approved 34-product stroller taxonomy")
        return 1
    return 1 if outcomes["CONFLICT"] or outcomes["ERROR"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
