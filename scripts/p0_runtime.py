"""P0 runtime primitives shared by FIELDNOTE scripts and the local API.

The module has no network dependencies.  It provides conservative filesystem
locks, atomically committed JSON/CSV/text payloads and centrally configured
subprocess timeouts.  Every writer keeps the previous valid file as a small
local recovery copy before replacing it.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence


PIPELINE_VERSION = "p0-run-coordinator-v1"
DEFAULT_STAGE_TIMEOUTS: dict[str, int] = {
    "targeted search": 180,
    "merge": 120,
    "fetch offer pages": 1_200,
    "technical cleaner": 300,
    "source registry": 300,
    "model groups": 300,
    "model facts cascade": 1_200,
    "model benchmark": 300,
    "coverage report": 300,
    "frontend snapshot": 300,
    "pipeline": 3_600,
}
LEASE_SECONDS = 45


class LockUnavailableError(RuntimeError):
    """Raised when another active run owns a lock for the same resource."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def lease_until(seconds: int = LEASE_SECONDS) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fsync_directory(path: Path) -> None:
    """Persist a rename where the platform exposes a directory file descriptor."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_staged(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return temporary


def _preserve_previous(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    backup = path.with_name(f"{path.name}.previous")
    staged = _write_staged(backup, path.read_bytes())
    os.replace(staged, backup)
    fsync_directory(path.parent)


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    validator: Callable[[Path], None] | None = None,
    preserve_previous: bool = True,
) -> None:
    """Write one file through a staged, fsynced and validated replacement."""
    temporary = _write_staged(path, content)
    try:
        if validator:
            validator(temporary)
        if preserve_previous:
            _preserve_previous(path)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(
    path: Path,
    content: str,
    *,
    validator: Callable[[Path], None] | None = None,
    preserve_previous: bool = True,
) -> None:
    atomic_write_bytes(path, content.encode("utf-8"), validator=validator, preserve_previous=preserve_previous)


def _validate_json_object(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, (dict, list)):
        raise ValueError("JSON payload must be an object or array.")


def atomic_write_json(path: Path, payload: Any, *, preserve_previous: bool = True) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, validator=_validate_json_object, preserve_previous=preserve_previous)


def _validate_csv(path: Path) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        csv.Sniffer().sniff(handle.read(4096) or ",")


def atomic_write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    *,
    preserve_previous: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in fieldnames} for row in rows])
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        _validate_csv(temporary)
        if preserve_previous:
            _preserve_previous(path)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_bundle(
    directory: Path,
    files: Mapping[str, bytes | str],
    *,
    json_files: set[str] | None = None,
) -> None:
    """Stage every derived cleaner artifact before any target is changed.

    Existing source inputs are never moved.  Each derived output is atomically
    replaced only after all staged files are complete.  `.previous` copies make
    recovery possible if the process is interrupted during the final sequence.
    The bundle manifest is committed last and marks a coherent version.
    """
    directory.mkdir(parents=True, exist_ok=True)
    json_files = json_files or set()
    staging = directory.parent / f".{directory.name}.bundle.{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        for name, value in files.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = value.encode("utf-8") if isinstance(value, str) else value
            with target.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if name in json_files:
                _validate_json_object(target)
        manifest = {
            "version": uuid.uuid4().hex,
            "committed_at": utc_now(),
            "files": sorted(files),
        }
        atomic_write_json(staging / ".p0_bundle_manifest.json", manifest, preserve_previous=False)
        for name in files:
            staged = staging / name
            target = directory / name
            if target.exists():
                _preserve_previous(target)
            os.replace(staged, target)
            fsync_directory(directory)
        committed_manifest = staging / ".p0_bundle_manifest.json"
        if (directory / ".p0_bundle_manifest.json").exists():
            _preserve_previous(directory / ".p0_bundle_manifest.json")
        os.replace(committed_manifest, directory / ".p0_bundle_manifest.json")
        fsync_directory(directory)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def process_is_alive(pid: int | str | None) -> bool:
    try:
        number = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if number <= 0:
        return False
    try:
        os.kill(number, 0)
    except OSError:
        return False
    return True


class FileLock:
    """A small JSON lock with ownership validation and explicit release."""

    def __init__(self, path: Path, payload: Mapping[str, Any]) -> None:
        self.path = path
        self.payload = dict(payload)
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps({**self.payload, "locked_at": utc_now()}, ensure_ascii=False, indent=2) + "\n"
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
            owner = str(existing.get("run_id", "unknown")) if isinstance(existing, dict) else "unknown"
            raise LockUnavailableError(f"Resource is already locked by run {owner}.") from exc
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            fsync_directory(self.path.parent)
            self.acquired = True
        except Exception:
            self.path.unlink(missing_ok=True)
            raise

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        if not current or current.get("run_id") == self.payload.get("run_id"):
            self.path.unlink(missing_ok=True)
            fsync_directory(self.path.parent)
        self.acquired = False

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.release()


@contextmanager
def global_aggregation_lock(lock_root: Path, run_id: str) -> Iterator[FileLock]:
    lock = FileLock(lock_root / "aggregation.lock", {"run_id": run_id, "scope": "global_aggregation"})
    with lock:
        yield lock


def stage_timeout(label: str) -> int:
    return int(DEFAULT_STAGE_TIMEOUTS.get(label, DEFAULT_STAGE_TIMEOUTS["pipeline"]))
