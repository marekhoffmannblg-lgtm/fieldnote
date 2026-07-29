#!/usr/bin/env python3
"""Explicit admin-only full derived-state rebuild."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fieldnote-api"))
from services.benchmark_rebuild_service import BenchmarkRebuildService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Pełny rebuild katalogu — wyłącznie akcja administracyjna.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="admin-full-rebuild")
    parser.add_argument("--lock-root", type=Path)
    args = parser.parse_args()
    service = BenchmarkRebuildService(lock_root=args.lock_root)
    result = service.rebuild_all_admin_state_file(args.input, args.output, run_id=args.run_id)
    print(json.dumps({"status": "ok", **result.metadata}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
