#!/usr/bin/env python3
"""Migrate read-only legacy run history into canonical RunManifestV1 files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from run_manifest import CANONICAL_RUNS_ROOT, legacy_run_entries, merge_legacy_entries, read_manifest, rebuild_index, save_manifest
from p0_runtime import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Migruje legacy historię runów bez usuwania źródeł.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--product-slug")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    manifests, conflicts = merge_legacy_entries(legacy_run_entries())
    if args.product_slug:
        manifests = [item for item in manifests if item.get("product_slug") == args.product_slug]
    planned = [item for item in manifests if not (args.resume and read_manifest(str(item["run_id"]), CANONICAL_RUNS_ROOT))]
    report = {
        "legacy_found": len(manifests), "migrated": len(planned), "skipped_existing": len(manifests) - len(planned),
        "conflicts": conflicts, "dry_run": args.dry_run,
    }
    if not args.dry_run:
        for manifest in planned:
            save_manifest(manifest)
        rebuild_index()
        atomic_write_json(CANONICAL_RUNS_ROOT / "migration_report.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
