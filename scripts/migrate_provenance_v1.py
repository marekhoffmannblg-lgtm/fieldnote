#!/usr/bin/env python3
"""Offline EvidenceItemV1 migration. It never fetches or changes field values."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from p0_runtime import atomic_write_json, atomic_write_text
from provenance_v1 import PROVENANCE_ROOT, ROOT, build_product_provenance


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalizuje provenance FIELDNOTE offline.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--product-slug")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("Wybierz --dry-run albo --apply")
    groups = sorted((ROOT / "output" / "model_groups").glob("*/group.json"))
    if args.product_slug:
        groups = [path for path in groups if path.parent.name == args.product_slug]
    migrated = unattributed = invalid = families = 0
    for group_path in groups:
        state_path = group_path.parent / "model_state.json"
        if not state_path.exists():
            continue
        import json
        try:
            group = json.loads(group_path.read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload = build_product_provenance(group_path.parent.name, group, state)
        items = [item for field in payload["fields"].values() for item in field["evidence_v1"]]
        migrated += len(items)
        unattributed += sum(item["evidence_status"] == "unattributed_legacy" for item in items)
        invalid += sum(item["validation_status"] == "invalid_reference" for item in items)
        families += len({item["content_family_id"] for item in items if item.get("content_family_id")})
        if args.apply:
            history = group_path.parent / "history" / "provenance_v1"
            history.mkdir(parents=True, exist_ok=True)
            backup = history / "model_state.before_provenance_v1.json"
            if not backup.exists():
                atomic_write_text(backup, state_path.read_text(encoding="utf-8"), preserve_previous=False)
            atomic_write_json(PROVENANCE_ROOT / f"{group_path.parent.name}.json", payload)
    print(f"provenance_records_migrated={migrated}")
    print(f"unattributed_legacy_count={unattributed}")
    print(f"invalid_source_references={invalid}")
    print(f"content_families_count={families}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
