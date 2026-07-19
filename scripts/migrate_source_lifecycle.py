#!/usr/bin/env python3
"""Build SourceRecordV1 from existing local registry, queue and snapshots."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from p0_runtime import atomic_write_text
from source_lifecycle import PROJECT_ROOT, REGISTRY_V1_PATH, build_source_records, read_source_records, write_source_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Migruje lifecycle źródeł bez pobierania sieciowego.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--product-slug")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if any(str(item.get("schema_version", "")) == "2" for item in read_source_records()):
        print(json.dumps({"status": "source_catalog_v2_already_active", "next_step": "migrate_product_source_links.py"}, ensure_ascii=False))
        return 0
    records = build_source_records()
    if args.product_slug:
        records = [item for item in records if item.get("product_slug") == args.product_slug]
    existing = {str(item.get("source_id")): item for item in read_source_records()} if args.resume else {}
    if args.resume and args.product_slug:
        merged = {**existing, **{str(item["source_id"]): item for item in records}}
        records = sorted(merged.values(), key=lambda item: str(item["source_id"]))
    report = {
        "records": len(records),
        "unassigned": sum(item["assignment"]["status"] == "unassigned" for item in records),
        "rejected": sum(item["assignment"]["status"] == "rejected" for item in records),
        "duplicates": sum(item["assignment"]["status"] == "duplicate" for item in records),
        "dry_run": args.dry_run,
    }
    if not args.dry_run:
        legacy_path = PROJECT_ROOT / "output" / "source_registry.jsonl"
        backup_path = PROJECT_ROOT / "output" / "source_registry_legacy_backup.jsonl"
        if legacy_path.exists() and not backup_path.exists():
            atomic_write_text(backup_path, legacy_path.read_text(encoding="utf-8"))
        write_source_records(records, REGISTRY_V1_PATH)
        from p0_runtime import atomic_write_json
        atomic_write_json(PROJECT_ROOT / "output" / "source_lifecycle_migration_report.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
