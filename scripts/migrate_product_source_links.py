#!/usr/bin/env python3
"""One-time offline split of global source identities from product links."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from p0_runtime import atomic_write_text
from source_lifecycle import (
    PRODUCT_SOURCE_LINKS_PATH,
    PROJECT_ROOT,
    REGISTRY_V1_PATH,
    build_product_source_links,
    globalize_source_record,
    read_source_records,
    write_product_source_links,
    write_source_records,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rozdziela globalne źródła od relacji produkt–źródło bez sieci.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    existing = read_source_records(REGISTRY_V1_PATH)
    if not existing:
        print(json.dumps({"source_catalog_count": 0, "product_source_links_count": 0, "dry_run": args.dry_run}, ensure_ascii=False))
        return 0

    # The operation is idempotent: V2 already contains global records.
    global_sources = [item if str(item.get("schema_version", "")) == "2" else globalize_source_record(item) for item in existing]
    source_ids = {str(item.get("source_id", "")) for item in global_sources}
    links = build_product_source_links(global_sources)
    if not args.dry_run:
        backup = PROJECT_ROOT / "output" / "source_registry_v1.pre_product_source_links_backup.jsonl"
        if REGISTRY_V1_PATH.exists() and not backup.exists():
            atomic_write_text(backup, REGISTRY_V1_PATH.read_text(encoding="utf-8"))
        write_source_records(global_sources, REGISTRY_V1_PATH)
        write_product_source_links(links, path=PRODUCT_SOURCE_LINKS_PATH, source_ids=source_ids)
    print(json.dumps({
        "source_catalog_count": len(global_sources),
        "product_source_links_count": len(links),
        "dry_run": args.dry_run,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
