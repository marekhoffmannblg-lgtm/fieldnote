"""Durable coordination for one local FIELDNOTE research run.

This module owns lock files and immutable run contexts.  It deliberately does
not know how the benchmark is built; the API and pipeline remain responsible
for their existing work.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from p0_runtime import (  # noqa: E402
    PIPELINE_VERSION,
    FileLock,
    LockUnavailableError,
    atomic_write_json,
    process_is_alive,
    utc_now,
)


RUN_STATUS_ACTIVE = {"queued", "running"}
RUN_STATUS_TERMINAL = {"succeeded", "failed", "timed_out", "cancelled", "interrupted"}


class RunCoordinator:
    def __init__(self, *, runs_root: Path, output_root: Path) -> None:
        self.runs_root = runs_root
        self.work_root = runs_root / "work"
        self.lock_root = output_root / "run_locks"
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.lock_root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, FileLock] = {}

    def manifest_path(self, run_id: str) -> Path:
        return self.runs_root / f"{run_id}.json"

    def product_lock_path(self, product_slug: str) -> Path:
        return self.lock_root / f"product-{product_slug}.lock"

    def work_directory(self, run_id: str) -> Path:
        return self.work_root / run_id

    def acquire_product(self, *, run_id: str, product_slug: str, group_key: str) -> None:
        lock = FileLock(
            self.product_lock_path(product_slug),
            {"run_id": run_id, "product_slug": product_slug, "group_key": group_key, "scope": "product"},
        )
        lock.acquire()
        self._locks[run_id] = lock

    def release_product(self, run_id: str) -> None:
        lock = self._locks.pop(run_id, None)
        if lock:
            lock.release()
            return
        # Recovery paths may run in a different API process.  Only remove a
        # lock if its manifest names the same run.
        for path in self.lock_root.glob("*.lock"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("run_id") == run_id:
                path.unlink(missing_ok=True)

    def create_context(self, payload: Mapping[str, Any], *, source_snapshot_paths: list[str]) -> dict[str, Any]:
        run_id = str(payload["run_id"])
        directory = self.work_directory(run_id)
        directory.mkdir(parents=True, exist_ok=False)
        try:
            working_directory = str(directory.relative_to(PROJECT_ROOT))
            selected_offers_csv = str((directory / "selected_new_offers.csv").relative_to(PROJECT_ROOT))
        except ValueError:
            # Fixture and recovery tests deliberately isolate state outside the
            # project directory.  The immutable context still records a stable,
            # explicit location without making the production layout special.
            working_directory = str(directory)
            selected_offers_csv = str(directory / "selected_new_offers.csv")
        context = {
            "run_id": run_id,
            "product_slug": str(payload.get("product_slug", "")),
            "group_key": str(payload.get("group_key", "")),
            "brand": str(payload.get("brand", "")),
            "model": str(payload.get("model", "")),
            "marketplace": str(payload.get("marketplace", "allegro")),
            "selected_offer_ids": list(payload.get("selected_offer_ids", [])),
            "source_snapshot_paths": list(source_snapshot_paths),
            "flags": dict(payload.get("flags", {})),
            "timestamps": {"created_at": utc_now()},
            "pipeline_version": PIPELINE_VERSION,
            "working_directory": working_directory,
            "selected_offers_csv": selected_offers_csv,
        }
        atomic_write_json(directory / "context.json", context, preserve_previous=False)
        return context

    def recover_orphaned_runs(self, read_manifest, save_manifest, status_updater) -> list[str]:
        """Mark stale active manifests interrupted after an API restart."""
        recovered: list[str] = []
        for path in self.runs_root.glob("*.json"):
            payload = read_manifest(path)
            if not isinstance(payload, dict) or payload.get("status") not in RUN_STATUS_ACTIVE:
                continue
            if process_is_alive(payload.get("child_pid")):
                continue
            payload.update({
                "status": "interrupted",
                "current_step": "Przerwano po restarcie lokalnego API",
                "error": "Proces potomny nie działa po restarcie API. Możesz ponowić ten run.",
                "finished_at": utc_now(),
                "last_heartbeat_at": utc_now(),
                "lease_expires_at": utc_now(),
            })
            save_manifest(payload)
            self.release_product(str(payload.get("run_id", "")))
            status_updater(payload)
            recovered.append(str(payload.get("run_id", "")))
        return recovered


__all__ = ["LockUnavailableError", "RunCoordinator", "RUN_STATUS_ACTIVE", "RUN_STATUS_TERMINAL"]
