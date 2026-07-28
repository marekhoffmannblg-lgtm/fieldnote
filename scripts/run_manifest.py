"""Canonical, versioned run-history records for FIELDNOTE.

The module deliberately uses only the standard library plus the existing P0
atomic writer.  It is shared by migrations and the local API, so an API
restart cannot create a second interpretation of the same run.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from p0_runtime import atomic_write_json


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_RUNS_ROOT = PROJECT_ROOT / "output" / "runs"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
RUN_TYPES = {"research", "refresh", "reanalysis", "migration"}
RUN_STATUSES = {"queued", "running", "partial", "succeeded", "failed", "timed_out", "cancelled", "interrupted"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_run_id(run_id: str) -> str:
    value = str(run_id or "").strip()
    if not RUN_ID_PATTERN.fullmatch(value):
        raise ValueError("Nieprawidłowy identyfikator uruchomienia.")
    return value


def canonical_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {"success": "succeeded", "preview": "succeeded", "error": "failed"}
    value = aliases.get(raw, raw)
    return value if value in RUN_STATUSES else "failed"


def canonical_run_type(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("run_type", "")).strip().lower()
    if explicit in RUN_TYPES:
        return explicit
    if payload.get("refresh"):
        return "refresh"
    if payload.get("analysis"):
        return "reanalysis"
    if payload.get("migration"):
        return "migration"
    return "research"


def default_manifest(run_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "run_id": safe_run_id(run_id),
        "product_slug": "",
        "group_key": "",
        "brand": "",
        "model": "",
        "run_type": "research",
        "status": "queued",
        "current_step": "",
        "progress": 0,
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "last_heartbeat_at": None,
        "retry_of": None,
        "selected_offer_ids": [],
        "source_ids": [],
        "sources_selected": 0,
        "sources_fetched": 0,
        "sources_failed": 0,
        "sources_attached": 0,
        "coverage_before": None,
        "coverage_after": None,
        "changed_fields": [],
        "new_conflicts": [],
        "error": None,
        "logs": [],
        "result_artifacts": {
            "model_state": None,
            "benchmark": None,
            "coverage": None,
            "frontend_snapshot": None,
            "history_snapshot": None,
        },
        "pipeline_version": "fieldnote-p1",
        "context_path": "",
        "updated_at": utc_now(),
    }


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any, fallback: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def _coverage(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def normalize_manifest(payload: dict[str, Any], *, legacy_incomplete: bool = False) -> dict[str, Any]:
    """Return V1 fields while preserving P0/API fields needed by live workers."""
    raw = dict(payload) if isinstance(payload, dict) else {}
    run_id = str(raw.get("run_id", "")).strip()
    if not run_id:
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]
        run_id = f"legacy-{digest}"
        legacy_incomplete = True
    result = default_manifest(run_id)
    result.update(raw)
    result["schema_version"] = "1"
    result["run_id"] = safe_run_id(run_id)
    result["run_type"] = canonical_run_type(raw)
    result["status"] = canonical_status(raw.get("status"))
    result["product_slug"] = str(raw.get("product_slug", "") or "")
    result["group_key"] = str(raw.get("group_key", "") or "")
    result["brand"] = str(raw.get("brand", "") or "")
    result["model"] = str(raw.get("model", "") or "")
    result["current_step"] = str(raw.get("current_step", "") or "")
    result["progress"] = min(100, _number(raw.get("progress")))
    result["created_at"] = str(raw.get("created_at") or raw.get("started_at") or raw.get("updated_at") or utc_now())
    result["started_at"] = raw.get("started_at")
    result["finished_at"] = raw.get("finished_at")
    result["last_heartbeat_at"] = raw.get("last_heartbeat_at")
    retry_of = raw.get("retry_of")
    result["retry_of"] = str(retry_of) if retry_of else None
    result["selected_offer_ids"] = [str(item) for item in _list(raw.get("selected_offer_ids")) if str(item)]
    result["source_ids"] = [str(item) for item in _list(raw.get("source_ids")) if str(item)]
    analysis = raw.get("analysis") if isinstance(raw.get("analysis"), dict) else {}
    result["sources_selected"] = _number(raw.get("sources_selected"), len(result["selected_offer_ids"]))
    result["sources_fetched"] = _number(raw.get("sources_fetched") or analysis.get("sources_fetched"))
    result["sources_failed"] = _number(raw.get("sources_failed") or analysis.get("sources_failed"))
    result["sources_attached"] = _number(raw.get("sources_attached") or analysis.get("sources_attached"))
    result["coverage_before"] = _coverage(raw.get("coverage_before") if raw.get("coverage_before") is not None else analysis.get("coverage_before"))
    result["coverage_after"] = _coverage(raw.get("coverage_after") if raw.get("coverage_after") is not None else analysis.get("coverage_after"))
    result["changed_fields"] = [str(item) for item in _list(raw.get("changed_fields"))]
    result["new_conflicts"] = [str(item) for item in _list(raw.get("new_conflicts"))]
    error = raw.get("error")
    result["error"] = str(error) if error else None
    result["logs"] = [str(item) for item in _list(raw.get("logs"))]
    artifacts = raw.get("result_artifacts") if isinstance(raw.get("result_artifacts"), dict) else {}
    result["result_artifacts"] = {key: artifacts.get(key) for key in default_manifest(run_id)["result_artifacts"]}
    result["pipeline_version"] = str(raw.get("pipeline_version") or "fieldnote-p1")
    result["context_path"] = str(raw.get("context_path") or raw.get("run_context_path") or "")
    result["updated_at"] = str(raw.get("updated_at") or utc_now())
    if legacy_incomplete:
        result["legacy_incomplete"] = True
    return result


def validate_manifest(payload: dict[str, Any]) -> None:
    value = normalize_manifest(payload)
    if value["status"] not in RUN_STATUSES or value["run_type"] not in RUN_TYPES:
        raise ValueError("Nieprawidłowy status lub typ uruchomienia.")
    if not isinstance(value["logs"], list) or not isinstance(value["selected_offer_ids"], list):
        raise ValueError("Manifest zawiera nieprawidłowe listy.")
    if not 0 <= value["progress"] <= 100:
        raise ValueError("Postęp musi mieścić się w przedziale 0–100.")


def run_directory(run_id: str, runs_root: Path = CANONICAL_RUNS_ROOT) -> Path:
    return runs_root / safe_run_id(run_id)


def manifest_path(run_id: str, runs_root: Path = CANONICAL_RUNS_ROOT) -> Path:
    return run_directory(run_id, runs_root) / "manifest.json"


def read_manifest(run_id: str, runs_root: Path = CANONICAL_RUNS_ROOT) -> dict[str, Any] | None:
    path = manifest_path(run_id, runs_root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return normalize_manifest(value) if isinstance(value, dict) else None


def index_record(manifest: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "run_id", "product_slug", "group_key", "brand", "model", "run_type", "status", "current_step", "progress",
        "created_at", "started_at", "finished_at", "last_heartbeat_at", "retry_of", "sources_selected", "sources_fetched",
        "sources_failed", "sources_attached", "coverage_before", "coverage_after", "error", "updated_at",
    )
    return {key: manifest.get(key) for key in keys}


def list_manifests(runs_root: Path = CANONICAL_RUNS_ROOT) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not runs_root.exists():
        return records
    for path in runs_root.glob("*/manifest.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            try:
                records.append(normalize_manifest(value))
            except ValueError:
                continue
    return records


def rebuild_index(runs_root: Path = CANONICAL_RUNS_ROOT) -> dict[str, Any]:
    records = sorted((index_record(item) for item in list_manifests(runs_root)), key=lambda item: str(item.get("created_at") or ""), reverse=True)
    index = {"schema_version": "1", "updated_at": utc_now(), "total": len(records), "runs": records}
    atomic_write_json(runs_root / "index.json", index)
    return index


def save_manifest(payload: dict[str, Any], *, runs_root: Path = CANONICAL_RUNS_ROOT, context: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = normalize_manifest(payload)
    validate_manifest(manifest)
    directory = run_directory(manifest["run_id"], runs_root)
    directory.mkdir(parents=True, exist_ok=True)
    if context is not None:
        atomic_write_json(directory / "context.json", context)
        manifest["context_path"] = str((directory / "context.json").relative_to(PROJECT_ROOT))
    atomic_write_json(directory / "manifest.json", manifest)
    logs = "\n".join(manifest["logs"])
    if logs:
        from p0_runtime import atomic_write_text
        atomic_write_text(directory / "logs.txt", logs + "\n")
    atomic_write_json(directory / "selected_sources.json", {"selected_offer_ids": manifest["selected_offer_ids"], "source_ids": manifest["source_ids"]})
    atomic_write_json(directory / "result_summary.json", {"status": manifest["status"], "coverage_before": manifest["coverage_before"], "coverage_after": manifest["coverage_after"], "changed_fields": manifest["changed_fields"], "error": manifest["error"]})
    rebuild_index(runs_root)
    return manifest


def legacy_run_entries(project_root: Path = PROJECT_ROOT) -> Iterable[tuple[Path, dict[str, Any]]]:
    api_root = project_root / "fieldnote-api" / "runs"
    for path in api_root.glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            yield path, value
    for path in (project_root / "output" / "research_runs").glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            yield path, value
    for path in (project_root / "output" / "model_groups").glob("*/history/*/refresh_manifest.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            yield path, value


def merge_legacy_entries(entries: Iterable[tuple[Path, dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deduplicate by run id; report incompatible copies without deleting them."""
    grouped: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path, raw in entries:
        run_id = str(raw.get("run_id", "")).strip()
        if not run_id:
            run_id = f"legacy-{hashlib.sha256(str(path).encode()).hexdigest()[:20]}"
            raw = {**raw, "run_id": run_id}
        grouped.setdefault(run_id, []).append((path, raw))
    manifests: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for run_id, values in grouped.items():
        values.sort(key=lambda item: (len(item[1]), str(item[1].get("updated_at") or item[1].get("finished_at") or "")), reverse=True)
        chosen_path, chosen = values[0]
        normalized = normalize_manifest(chosen, legacy_incomplete=not bool(chosen.get("product_slug")))
        normalized["legacy_sources"] = [str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else str(path) for path, _ in values]
        manifests.append(normalized)
        fingerprints: set[str] = set()
        for _, raw in values:
            comparable = normalize_manifest(raw, legacy_incomplete=not bool(raw.get("product_slug")))
            # `updated_at` is synthesized for incomplete legacy manifests and
            # must not turn byte-identical history copies into a conflict.
            comparable.pop("updated_at", None)
            comparable.pop("created_at", None)
            fingerprints.add(json.dumps(comparable, sort_keys=True, ensure_ascii=False))
        if len(fingerprints) > 1:
            conflicts.append({"run_id": run_id, "chosen": str(chosen_path), "paths": [str(path) for path, _ in values], "reason": "conflicting_legacy_manifests"})
    return manifests, conflicts
