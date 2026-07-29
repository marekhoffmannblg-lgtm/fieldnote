#!/usr/bin/env python3
"""Rebuild one product scope from a fixture/repository state.

This command is intentionally explicit: it never scans the global catalogue and
never invokes the frontend export.  The admin full rebuild has a separate CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fieldnote-api"))
from services.benchmark_rebuild_service import BenchmarkRebuildService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Przyrostowy rebuild jednego produktu.")
    parser.add_argument("--input", type=Path, required=True, help="JSON state/fixture.")
    parser.add_argument("--output", type=Path, required=True, help="Docelowy JSON state.")
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--updates", type=Path, help="Opcjonalny JSON z polami zmienionego produktu.")
    parser.add_argument("--run-id", default="scoped-rebuild")
    parser.add_argument("--lock-root", type=Path)
    args = parser.parse_args()
    updates = None
    if args.updates:
        value = json.loads(args.updates.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SystemExit("--updates musi wskazywać obiekt JSON")
        updates = value
    service = BenchmarkRebuildService(lock_root=args.lock_root)
    result = service.rebuild_product_state_file(args.input, args.output, args.product_id, updates=updates, run_id=args.run_id)
    print(json.dumps({"status": "ok", **result.metadata}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
