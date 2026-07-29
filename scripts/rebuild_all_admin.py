#!/usr/bin/env python3
"""Explicit admin-only full derived-state rebuild."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fieldnote-api"))
from services.benchmark_rebuild_service import BenchmarkRebuildService, read_state, write_state  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Pełny rebuild katalogu — wyłącznie akcja administracyjna.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="admin-full-rebuild")
    parser.add_argument("--lock-root", type=Path)
    args = parser.parse_args()
    result = BenchmarkRebuildService(lock_root=args.lock_root).rebuild_all_admin(read_state(args.input), run_id=args.run_id)
    write_state(args.output, result.state)
    print(json.dumps({"status": "ok", **result.metadata}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
