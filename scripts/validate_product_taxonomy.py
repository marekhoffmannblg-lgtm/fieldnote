#!/usr/bin/env python3
"""Validate generated Lionelo taxonomy without changing any data."""
from __future__ import annotations

import csv
import json
import argparse
import hashlib
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = ROOT / "output" / "taxonomy"
ARTIFACTS = (
    "FIELDNOTE_product_inventory_classified.csv",
    "category_registry.json",
    "benchmark_groups.csv",
    "benchmark_attribute_candidates.csv",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structural-only", action="store_true", help="Skip semantic taxonomy checks.")
    parser.add_argument("--verify-reproducible", action="store_true", help="Regenerate four artifacts in a temporary directory and compare bytes.")
    parser.add_argument("--input", type=Path, default=Path.home() / "Downloads" / "FIELDNOTE_product_inventory.csv")
    parser.add_argument("--spec-xlsx", type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    with (TAXONOMY / "FIELDNOTE_product_inventory_classified.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    registry = json.loads((TAXONOMY / "category_registry.json").read_text(encoding="utf-8"))
    groups = list(csv.DictReader((TAXONOMY / "benchmark_groups.csv").open(encoding="utf-8", newline="")))
    attributes = list(csv.DictReader((TAXONOMY / "benchmark_attribute_candidates.csv").open(encoding="utf-8", newline="")))
    registry_groups = {g["key"] for category in registry.get("categories", []) for sub in category.get("subcategories", []) for g in sub.get("benchmark_groups", [])}
    registry_categories = {c["key"] for c in registry.get("categories", [])}
    registry_subcategories = {s["key"] for c in registry.get("categories", []) for s in c.get("subcategories", [])}
    from build_lionelo_product_taxonomy import CATEGORY_LABELS, GROUPS, SUBCATEGORY_LABELS
    data_categories = {r.get("category_key") for r in rows}
    data_subcategories = {r.get("subcategory_key") for r in rows}
    data_groups = {r.get("benchmark_group_key") for r in rows if r.get("benchmark_group_key")}
    if data_categories != registry_categories:
        errors.append("registry categories do not exactly match generated data")
    if not data_categories <= set(CATEGORY_LABELS):
        errors.append("generated data contains a category unknown to the generator")
    if not registry_categories <= set(CATEGORY_LABELS):
        errors.append("registry contains a category unknown to the generator")
    if not data_subcategories <= set(SUBCATEGORY_LABELS):
        errors.append("generated data contains a subcategory unknown to the generator")
    if not data_groups <= set(GROUPS):
        errors.append("generated data contains a benchmark group unknown to the generator")
    for index, row in enumerate(rows, start=2):
        if not row.get("category_key"): errors.append(f"row {index}: missing category")
        if not row.get("subcategory_key"): errors.append(f"row {index}: missing subcategory")
        if not row.get("benchmark_group_key") and row.get("benchmarkable") != "no": errors.append(f"row {index}: missing benchmark group")
        if row.get("category_key") not in registry_categories: errors.append(f"row {index}: unknown category")
        if row.get("subcategory_key") not in registry_subcategories: errors.append(f"row {index}: unknown subcategory")
        if row.get("benchmark_group_key") and row.get("benchmark_group_key") not in registry_groups: errors.append(f"row {index}: unknown benchmark group")
        if row.get("classification_confidence") == "low" and row.get("review_required") != "true": errors.append(f"row {index}: low confidence without review")
    identities = [(r.get("brand", ""), r.get("product_name", "")) for r in rows]
    duplicates = [key for key, count in Counter(identities).items() if count > 1]
    if duplicates: errors.append(f"duplicate products: {duplicates}")
    for group in groups:
        if not group.get("definition") or not group.get("include_rules") or not group.get("exclude_rules"): errors.append(f"group {group.get('benchmark_group_key')}: incomplete rules")
        actual = sum(r.get("benchmark_group_key") == group.get("benchmark_group_key") for r in rows)
        if actual != int(group.get("lionelo_product_count", "-1")): errors.append(f"group {group.get('benchmark_group_key')}: count mismatch")
        if group.get("include_rules") == "produkt spełnia definicję grupy" or group.get("exclude_rules") == "inny typ produktu; dedykowana część": errors.append(f"group {group.get('benchmark_group_key')}: placeholder rules")
        if group.get("benchmarkable") == "yes" and sum(a["benchmark_group_key"] == group["benchmark_group_key"] for a in attributes) < 5: errors.append(f"group {group.get('benchmark_group_key')}: fewer than five attributes")
    if not args.structural_only:
        if any(r.get("benchmark_group_key") == "baby_monitor_unspecified" for r in rows): errors.append("unspecified baby monitors despite specification data")
        for row in rows:
            name = row.get("product_name", "")
            group = row.get("benchmark_group_key", "")
            if name == "BABYBLISS" and group != "wipe_warmer": errors.append("BABYBLISS is not a wipe warmer")
            if name in {"Flexigrip", "PureBin", "Helmet"} and group == "care_accessory": errors.append(f"{name}: unrelated care accessory")
        prohibited = {"masa", "wymiary po złożeniu", "koła i amortyzacja", "udźwig"}
        stroller_accessory_attributes = {a["attribute_candidate"] for a in attributes if a["benchmark_group_key"] == "stroller_accessory"}
        if stroller_accessory_attributes & prohibited: errors.append("stroller accessory inherits stroller attributes")
        car_accessory_attributes = {a["attribute_candidate"] for a in attributes if a["benchmark_group_key"] == "car_seat_accessory"}
        if car_accessory_attributes & {"zakres wzrostu", "sposób montażu", "norma bezpieczeństwa"}: errors.append("car seat accessory inherits car seat attributes")
        signatures: dict[tuple[str, ...], list[str]] = {}
        for group in {a["benchmark_group_key"] for a in attributes}:
            signature = tuple(sorted(a["attribute_candidate"] for a in attributes if a["benchmark_group_key"] == group))
            signatures.setdefault(signature, []).append(group)
        for signature, group_keys in signatures.items():
            if len(signature) >= 5 and len(group_keys) > 1: errors.append(f"identical attribute set for unrelated groups: {group_keys}")
        expected_subcategories = {
            "BABYBLISS": "wipe_warmers",
            "BabyAir Flow": "nasal_aspirators",
            "Nebi Air Mask": "nebulizers",
            "FeverScan": "thermometers",
            "BabyBalance": "baby_scales",
            "Bamboo Blanket": "baby_blankets",
            "Bamboo Swaddle": "swaddles_and_muslins",
            "Bamboo Sheet": "baby_bedding",
            "Muslin Hooded Towel": "bath_textiles",
        }
        by_name = {row.get("product_name"): row for row in rows}
        for product_name, subcategory in expected_subcategories.items():
            if by_name.get(product_name, {}).get("subcategory_key") != subcategory:
                errors.append(f"{product_name}: expected semantic subcategory {subcategory}")
        if any(row.get("source_tab") == "TEKSTYLIA" and row.get("category_key") != "textiles" for row in rows):
            errors.append("textiles are classified outside the textiles category")
        if any(row.get("source_tab") == "TEKSTYLIA" and row.get("benchmark_group_key") == "care_accessory" for row in rows):
            errors.append("textiles are classified as care accessories")
    if args.verify_reproducible:
        if not args.spec_xlsx:
            errors.append("--verify-reproducible requires --spec-xlsx")
        else:
            with tempfile.TemporaryDirectory(prefix="fieldnote-taxonomy-") as directory:
                regenerated = Path(directory)
                command = [
                    sys.executable,
                    str(ROOT / "scripts" / "build_lionelo_product_taxonomy.py"),
                    "--input", str(args.input),
                    "--spec-xlsx", str(args.spec_xlsx),
                    "--output", str(regenerated),
                ]
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                if result.returncode:
                    errors.append("reproducibility generator failed")
                else:
                    for filename in ARTIFACTS:
                        if not (regenerated / filename).is_file() or sha256(TAXONOMY / filename) != sha256(regenerated / filename):
                            errors.append(f"reproducibility mismatch: {filename}")
    print(f"products_checked={len(rows)}")
    print(f"groups_checked={len(groups)}")
    label = "structural_validation" if args.structural_only else "semantic_validation"
    print(f"{label}={'PASS' if not errors else 'FAIL'}")
    if errors:
        for error in errors: print(f"FAIL: {error}")
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
