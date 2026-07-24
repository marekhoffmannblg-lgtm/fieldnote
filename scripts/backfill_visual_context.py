"""Build shared visual context from cached source HTML without network access."""

from __future__ import annotations

import argparse
from pathlib import Path

from visual_snapshots import ROOT, artifact_directory, extract_visual_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline backfill wizualnego kontekstu zapisanych źródeł.")
    parser.add_argument("--all", action="store_true", help="Przetwórz wszystkie źródła z lokalnym HTML.")
    parser.add_argument("--product-slug", default="")
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Przebuduj kontekst mimo niezmienionego HTML.")
    return parser.parse_args()


def discover(product_slug: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    manufacturer_root = ROOT / "input" / "manufacturer_sources"
    for metadata in manufacturer_root.glob("*/*/metadata.json"):
        if product_slug and metadata.parent.parent.name != product_slug:
            continue
        import json
        try:
            value = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_id = str(value.get("source_id", ""))
        if source_id and (metadata.parent / "page.html").exists():
            entries.append((source_id, metadata.parent.parent.name))
    for html in (ROOT / "input" / "firecrawl_offer_pages").glob("*/html.html"):
        offer_id = html.parent.name
        entries.append((f"allegro:{offer_id}", product_slug))
    return entries


def main() -> int:
    args = parse_args()
    if not args.apply and not args.dry_run:
        print("Podaj --apply, aby zapisać artefakty, albo --dry-run.")
        return 2
    targets = [(source_id, args.product_slug) for source_id in args.source_id]
    if args.all:
        targets.extend(discover(args.product_slug))
    if not targets:
        print("sources=0")
        return 0
    seen: set[str] = set()
    written = skipped = failed = 0
    for source_id, product_slug in targets:
        if source_id in seen:
            continue
        seen.add(source_id)
        directory = artifact_directory(source_id, product_slug)
        if directory is None:
            print(f"warning=missing_artifacts source_id={source_id}")
            failed += 1
            continue
        if args.dry_run:
            print(f"would_backfill={source_id}")
            continue
        try:
            result = extract_visual_context(source_id, product_slug=product_slug, directory=directory, refresh=args.refresh)
            if result["status"] == "skipped":
                skipped += 1
            else:
                written += 1
            print(f"source_id={source_id} blocks={result['blocks']} media={result['media']} status={result['status']}")
        except (OSError, ValueError, FileNotFoundError) as error:
            failed += 1
            print(f"warning=visual_backfill_failed source_id={source_id} error={error}")
    print(f"sources={len(seen)}")
    print(f"written={written}")
    print(f"skipped={skipped}")
    print(f"failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
