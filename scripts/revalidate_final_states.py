"""Offline, sequential P1 revalidation of persisted final model states."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from p0_runtime import atomic_write_bytes, atomic_write_json
from quality_gate import FIELDS, apply_quality_gate, load_registry


ROOT = Path(__file__).resolve().parent.parent
GROUPS = ROOT / "output" / "model_groups"
QUALITY_ROOT = ROOT / "output" / "quality_gate"
PRODUCT_STATE_PATH = ROOT / "output" / "product_state.json"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def product_state_update(product_slug: str, has_reliable_fields: bool) -> None:
    state = read_json(PRODUCT_STATE_PATH)
    entry = state.get(product_slug, {}) if isinstance(state.get(product_slug), dict) else {}
    entry.update({"product_slug": product_slug, "updated_at": utc_now()})
    if has_reliable_fields:
        entry.update({"result_status": "ready", "refresh_recommended": False, "refresh_reason": None})
    else:
        entry.update({
            "result_status": "invalid",
            "refresh_recommended": True,
            "refresh_reason": "quality_gate_rejected_all_fields",
        })
    entry.setdefault("active_run_status", "none")
    entry.setdefault("last_successful_run_id", None)
    entry.setdefault("last_failed_run_id", None)
    entry.setdefault("last_successful_at", None)
    entry.setdefault("last_failed_at", None)
    state[product_slug] = entry
    atomic_write_json(PRODUCT_STATE_PATH, state)


def history_backup(state_path: Path) -> Path:
    history = state_path.parent / "history" / f"{utc_stamp()}__p1_quality_gate"
    history.mkdir(parents=True, exist_ok=False)
    atomic_write_bytes(history / "model_state.before_quality_gate.json", state_path.read_bytes(), preserve_previous=False)
    group_path = state_path.parent / "group.json"
    if group_path.exists():
        atomic_write_bytes(history / "group.before_quality_gate.json", group_path.read_bytes(), preserve_previous=False)
    return history


def first_quality_gate_fields_before(state_path: Path, fallback: int) -> int:
    """Keep the P1 report stable when an offline revalidation is repeated."""
    backups = sorted(state_path.parent.glob("history/*__p1_quality_gate/model_state.before_quality_gate.json"))
    if not backups:
        return fallback
    original = read_json(backups[0])
    return sum(
        1 for field in original.get("fields", {}).values()
        if isinstance(field, dict) and field.get("value", "X") != "X"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group-key")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    registry = load_registry()
    rows: list[dict[str, Any]] = []
    for state_path in sorted(GROUPS.glob("*/model_state.json")):
        group = read_json(state_path.parent / "group.json")
        state = read_json(state_path)
        group_key = str(state.get("group_key", group.get("group_key", "")))
        if args.group_key and group_key != args.group_key:
            continue
        if not state.get("fields"):
            continue
        before = sum(1 for field in state.get("fields", {}).values() if isinstance(field, dict) and field.get("value", "X") != "X")
        initial_before = first_quality_gate_fields_before(state_path, before)
        gated, report = apply_quality_gate(state, group, registry)
        product_slug = state_path.parent.name
        report["product_slug"] = product_slug
        report["fields_before"] = initial_before
        report["fields_total"] = len(FIELDS)
        report["revalidated_at"] = utc_now()
        report["history_backup"] = ""
        reliable = report["fields_valid"] + report["fields_weak"]
        if not args.dry_run:
            history = history_backup(state_path)
            report["history_backup"] = str(history.relative_to(ROOT))
            atomic_write_json(state_path, gated)
            product_state_update(product_slug, reliable > 0)
        QUALITY_ROOT.mkdir(parents=True, exist_ok=True)
        atomic_write_json(QUALITY_ROOT / f"{product_slug}.json", report)
        rows.append({"group_key": group_key, "product_slug": product_slug, "fields_before": before, **report})
        print(
            f"product={product_slug} valid={report['fields_valid']} weak={report['fields_weak']} "
            f"conflicting={report['fields_conflicting']} rejected={report['fields_rejected']}"
        )
    print(f"products_revalidated={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
