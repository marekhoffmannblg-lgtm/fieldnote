"""Build the canonical P0 product lifecycle state from existing local outputs.

This migration reads only existing group, benchmark, coverage and legacy status
files. It never changes model_state fields, snapshots or source registry.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from p0_runtime import atomic_write_json


ROOT = Path(__file__).resolve().parent.parent
GROUPS = ROOT / "output" / "model_groups"
BENCHMARK = ROOT / "output" / "model_benchmark.csv"
COVERAGE = ROOT / "output" / "model_coverage.csv"
LEGACY = ROOT / "output" / "product_analysis_status.json"
STATE = ROOT / "output" / "product_state.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def csv_group_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        return {str(row.get("group_key", "")).strip() for row in csv.DictReader(handle) if row.get("group_key")}


def main() -> int:
    benchmark_keys = csv_group_keys(BENCHMARK)
    coverage_keys = csv_group_keys(COVERAGE)
    legacy = read_json(LEGACY)
    legacy = legacy if isinstance(legacy, dict) else {}
    states: dict[str, dict[str, Any]] = {}
    for group_path in sorted(GROUPS.glob("*/group.json")):
        group = read_json(group_path)
        if not isinstance(group, dict):
            continue
        slug = group_path.parent.name
        key = str(group.get("group_key", ""))
        fields = read_json(group_path.parent / "model_state.json")
        fields = fields.get("fields", {}) if isinstance(fields, dict) else {}
        valid = bool(fields) and key in benchmark_keys and key in coverage_keys
        old = legacy.get(slug, {}) if isinstance(legacy.get(slug, {}), dict) else {}
        old_status = str(old.get("status", ""))
        old_error = str(old.get("error", ""))
        state: dict[str, Any] = {
            "product_slug": slug,
            "result_status": "ready" if valid else "invalid" if old_status == "analysis_failed" else "none",
            "active_run_status": "none",
            "last_successful_run_id": "legacy-bootstrap" if valid else None,
            "last_failed_run_id": "legacy-bootstrap" if old_status == "analysis_failed" else None,
            "last_successful_at": str(old.get("updated_at", "")) if valid else None,
            "last_failed_at": str(old.get("updated_at", "")) if old_status == "analysis_failed" else None,
            "refresh_recommended": bool(valid and old_status in {"analysis_failed", "refresh_recommended"}),
            "refresh_reason": old_error or ("Dane wymagają odświeżenia." if valid and old_status == "refresh_recommended" else None),
            "updated_at": now(),
        }
        states[slug] = state
    atomic_write_json(STATE, states)
    print(f"product_states_bootstrapped={len(states)}")
    print(f"ready_states={sum(item['result_status'] == 'ready' for item in states.values())}")
    print(f"invalid_states={sum(item['result_status'] == 'invalid' for item in states.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
