"""Deterministic, scoped benchmark rebuild primitives.

The durable worker can use this module as an adapter around the source of truth
(Supabase in production, JSON fixtures in the offline gate).  It deliberately
does not discover products or run a global export during a product rebuild.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from p0_runtime import FileLock, LockUnavailableError, atomic_write_json  # noqa: E402


VOLATILE_KEYS = {"created_at", "updated_at", "run_id", "stage", "path", "generated_at", "research_runs"}


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0])) if str(key) not in VOLATILE_KEYS}
    if isinstance(value, list):
        values = [_stable(item) for item in value]
        return sorted(values, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return value


def semantic_hash(value: Any) -> str:
    payload = json.dumps(_stable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def price_change_requires_snapshot(before: Any, after: Any, threshold: float = 0.05) -> bool:
    """Return whether a price move is significant (5% by default)."""
    try:
        old, new = float(before), float(after)
    except (TypeError, ValueError):
        return before != after
    if old == new:
        return False
    if old == 0:
        return True
    return abs(new - old) / abs(old) >= threshold


def _id(item: Mapping[str, Any]) -> str:
    for key in ("product_id", "id", "group_key", "benchmark_id", "source_id", "evidence_id"):
        if str(item.get(key, "")).strip():
            return str(item[key])
    return ""


def _lock_component(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in value)[:180] or "unknown"


def _contains_product(item: Mapping[str, Any], product_id: str) -> bool:
    if str(item.get("product_id", "")) == product_id or str(item.get("anchor_product_id", "")) == product_id:
        return True
    values = item.get("product_ids", item.get("participant_product_ids", []))
    return product_id in {str(value) for value in values} if isinstance(values, list) else False


def product_scope(state: Mapping[str, Any], product_id: str) -> dict[str, Any]:
    """Return the exact product, evidence, sources and affected benchmarks."""
    products = [item for item in state.get("products", []) if isinstance(item, Mapping)]
    target = next((item for item in products if str(item.get("product_id", item.get("id", ""))) == product_id), None)
    if target is None:
        raise KeyError(f"Unknown product_id: {product_id}")
    group_key = str(target.get("group_key", ""))
    benchmark_group = str(target.get("benchmark_group", target.get("benchmark_group_key", "")))
    return {
        "product_id": product_id,
        "product_slug": str(target.get("product_slug", target.get("slug", ""))),
        "group_key": group_key,
        "category_key": str(target.get("category_key", "")),
        "benchmark_group": benchmark_group,
        "products": [copy.deepcopy(target)],
        "sources": [copy.deepcopy(item) for item in state.get("sources", []) if isinstance(item, Mapping) and (_contains_product(item, product_id) or str(item.get("group_key", "")) == group_key)],
        "evidence": [copy.deepcopy(item) for item in state.get("evidence", []) if isinstance(item, Mapping) and (_contains_product(item, product_id) or str(item.get("group_key", "")) == group_key)],
        "competitive_benchmarks": [copy.deepcopy(item) for item in state.get("competitive_benchmarks", []) if isinstance(item, Mapping) and _contains_product(item, product_id)],
        "internal_benchmarks": [copy.deepcopy(item) for item in state.get("internal_benchmarks", []) if isinstance(item, Mapping) and str(item.get("benchmark_group", item.get("benchmark_group_key", ""))) == benchmark_group],
    }


def benchmark_group_scope(state: Mapping[str, Any], benchmark_group: str) -> dict[str, Any]:
    products = [copy.deepcopy(item) for item in state.get("products", []) if isinstance(item, Mapping) and str(item.get("benchmark_group", item.get("benchmark_group_key", ""))) == benchmark_group]
    product_ids = {str(item.get("product_id", item.get("id", ""))) for item in products}
    return {
        "benchmark_group": benchmark_group,
        "product_ids": sorted(product_ids),
        "products": products,
        "internal_benchmarks": [copy.deepcopy(item) for item in state.get("internal_benchmarks", []) if isinstance(item, Mapping) and str(item.get("benchmark_group", item.get("benchmark_group_key", ""))) == benchmark_group],
        "competitive_benchmarks": [copy.deepcopy(item) for item in state.get("competitive_benchmarks", []) if isinstance(item, Mapping) and any(_contains_product(item, product_id) for product_id in product_ids)],
    }


def _replace_by_id(items: list[Any], replacement: Mapping[str, Any], keys: tuple[str, ...]) -> list[Any]:
    replacement_id = next((str(replacement.get(key, "")) for key in keys if str(replacement.get(key, ""))), "")
    result = [item for item in items if not isinstance(item, Mapping) or next((str(item.get(key, "")) for key in keys if str(item.get(key, ""))), "") != replacement_id]
    result.append(copy.deepcopy(dict(replacement)))
    return result


def _product_payload(state: Mapping[str, Any], target: Mapping[str, Any], product_id: str) -> dict[str, Any]:
    group_key = str(target.get("group_key", ""))
    return {
        "product": target,
        "sources": [item for item in state.get("sources", []) if isinstance(item, Mapping) and (_contains_product(item, product_id) or str(item.get("group_key", "")) == group_key)],
        "evidence": [item for item in state.get("evidence", []) if isinstance(item, Mapping) and (_contains_product(item, product_id) or str(item.get("group_key", "")) == group_key)],
        "competitive_benchmarks": [item for item in state.get("competitive_benchmarks", []) if isinstance(item, Mapping) and _contains_product(item, product_id)],
        "internal_benchmark": [item for item in state.get("internal_benchmarks", []) if isinstance(item, Mapping) and str(item.get("benchmark_group", item.get("benchmark_group_key", ""))) == str(target.get("benchmark_group", ""))],
    }


def _apply_product(state: dict[str, Any], product_id: str, updates: Mapping[str, Any] | None, *, create_snapshot: bool = True) -> dict[str, Any]:
    products = [item for item in state.get("products", []) if isinstance(item, Mapping)]
    index = next((idx for idx, item in enumerate(products) if str(item.get("product_id", item.get("id", ""))) == product_id), None)
    if index is None:
        raise KeyError(f"Unknown product_id: {product_id}")
    target = dict(products[index])
    if updates:
        target.update({str(key): copy.deepcopy(value) for key, value in updates.items() if str(key) not in {"product_id", "id"}})
    products[index] = target
    state["products"] = products
    payload = _product_payload(state, target, product_id)
    product_hash = semantic_hash(payload)
    domain_payload = copy.deepcopy(payload)
    if isinstance(domain_payload.get("product"), Mapping):
        domain_payload["product"] = {key: value for key, value in domain_payload["product"].items() if key != "price"}
    domain_hash = semantic_hash(domain_payload)
    snapshots = [item for item in state.get("benchmark_snapshots", []) if isinstance(item, Mapping)]
    existing = next((item for item in snapshots if item.get("scope_type") == "product" and str(item.get("scope_id")) == product_id), None)
    changed = existing is None or str(existing.get("semantic_hash")) != product_hash
    price_changed = price_change_requires_snapshot((existing or {}).get("price"), target.get("price")) if existing else True
    snapshot_created = bool(create_snapshot and changed and (existing is None or price_changed or domain_hash != str(existing.get("domain_hash", ""))))
    if snapshot_created:
        snapshots = [item for item in snapshots if not (item.get("scope_type") == "product" and str(item.get("scope_id")) == product_id)]
        snapshots.append({"scope_type": "product", "scope_id": product_id, "semantic_hash": product_hash, "domain_hash": domain_hash, "price": target.get("price"), "group_key": target.get("group_key", "")})
    state["benchmark_snapshots"] = snapshots
    group = str(target.get("benchmark_group", target.get("benchmark_group_key", "")))
    if group:
        group_products = [item for item in state["products"] if str(item.get("benchmark_group", item.get("benchmark_group_key", ""))) == group]
        group_payload = {"benchmark_group": group, "products": group_products, "internal_benchmarks": [item for item in state.get("internal_benchmarks", []) if str(item.get("benchmark_group", item.get("benchmark_group_key", ""))) == group]}
        group_hash = semantic_hash(group_payload)
        group_snaps = [item for item in state.get("benchmark_group_snapshots", []) if isinstance(item, Mapping) and str(item.get("scope_id")) != group]
        group_snaps.append({"scope_type": "benchmark_group", "scope_id": group, "semantic_hash": group_hash})
        state["benchmark_group_snapshots"] = group_snaps
    competitive_snaps = [item for item in state.get("competitive_benchmark_snapshots", []) if isinstance(item, Mapping)]
    for benchmark in state.get("competitive_benchmarks", []):
        if not isinstance(benchmark, Mapping) or not _contains_product(benchmark, product_id):
            continue
        benchmark_id = str(benchmark.get("benchmark_id", benchmark.get("id", "")))
        participant_ids = benchmark.get("participant_product_ids", benchmark.get("product_ids", []))
        participant_products = [item for item in state["products"] if isinstance(item, Mapping) and str(item.get("product_id", item.get("id", ""))) in {str(value) for value in participant_ids}]
        benchmark_hash = semantic_hash({"benchmark": benchmark, "products": participant_products})
        competitive_snaps = [item for item in competitive_snaps if str(item.get("scope_id")) != benchmark_id]
        competitive_snaps.append({"scope_type": "competitive_benchmark", "scope_id": benchmark_id, "semantic_hash": benchmark_hash})
    state["competitive_benchmark_snapshots"] = competitive_snaps
    return {"product_id": product_id, "group_key": target.get("group_key", ""), "benchmark_group": group, "snapshot_created": snapshot_created, "semantic_hash": product_hash}


@dataclass(frozen=True)
class RebuildResult:
    state: dict[str, Any]
    metadata: dict[str, Any]


class BenchmarkRebuildService:
    """Repository-neutral service used by scripts and the durable worker."""

    def __init__(self, *, lock_root: Path | None = None, critical_section_hook: Callable[[str, str], None] | None = None) -> None:
        self.lock_root = Path(lock_root) if lock_root else PROJECT_ROOT / "output" / "run_locks"
        # Offline fixture tests can inject a barrier at the lock boundary to
        # prove read/merge/write serialization without relying on scheduler
        # timing. Production callers leave this unset.
        self.critical_section_hook = critical_section_hook

    def _critical_section(self, phase: str, scope: str) -> None:
        if self.critical_section_hook is not None:
            self.critical_section_hook(phase, scope)

    @contextmanager
    def aggregation_transaction(self, *, run_id: str, scope: str, wait_seconds: float = 5.0) -> Iterator[None]:
        """Serialize a complete file-fixture read/merge/write transaction.

        Production uses the fenced PostgreSQL commit RPC. This bounded retry is
        the equivalent safety boundary for offline JSON fixtures and explicit
        operator CLIs: a competing scope waits rather than overwriting a
        freshly committed state from another scope.
        """
        lock = FileLock(self.lock_root / "aggregation.lock", {"run_id": run_id, "scope": scope})
        self._critical_section("before_acquire", scope)
        deadline = time.monotonic() + max(0, wait_seconds)
        while True:
            try:
                lock.acquire()
                break
            except LockUnavailableError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
        try:
            self._critical_section("acquired", scope)
            yield
        finally:
            lock.release()

    def rebuild_product_scope(self, state: Mapping[str, Any], product_id: str, *, updates: Mapping[str, Any] | None = None, run_id: str = "scoped-rebuild", lock_already_held: bool = False) -> RebuildResult:
        working = copy.deepcopy(dict(state))
        scope = product_scope(working, product_id)
        lock = FileLock(self.lock_root / "aggregation.lock", {"run_id": run_id, "scope": "scoped_derived_commit", "product_id": product_id})
        if lock_already_held:
            metadata = _apply_product(working, product_id, updates)
        else:
            with lock:
                metadata = _apply_product(working, product_id, updates)
        working.setdefault("research_runs", []).append({"run_id": run_id, "scope_type": "product", "scope_id": product_id, "snapshot_created": metadata["snapshot_created"], "semantic_hash": metadata["semantic_hash"]})
        metadata.update({"run_id": run_id, "scope": scope})
        return RebuildResult(working, metadata)

    def rebuild_all_admin(self, state: Mapping[str, Any], *, run_id: str = "admin-full-rebuild", lock_already_held: bool = False) -> RebuildResult:
        working = copy.deepcopy(dict(state))
        lock = FileLock(self.lock_root / "aggregation.lock", {"run_id": run_id, "scope": "admin_full_rebuild"})
        def apply() -> dict[str, Any]:
            products = sorted((item for item in working.get("products", []) if isinstance(item, Mapping)), key=lambda item: str(item.get("product_id", item.get("id", ""))))
            metadata = {"run_id": run_id, "scope": "full", "product_ids": []}
            for item in products:
                product_id = str(item.get("product_id", item.get("id", "")))
                if product_id:
                    metadata["product_ids"].append(product_id)
                    _apply_product(working, product_id, None)
            working.setdefault("research_runs", []).append({"run_id": run_id, "scope_type": "full", "scope_id": "catalog", "product_ids": metadata["product_ids"]})
            return metadata
        if lock_already_held:
            metadata = apply()
        else:
            with lock:
                metadata = apply()
        return RebuildResult(working, metadata)

    def rebuild_product_state_file(self, input_path: Path, output_path: Path, product_id: str, *, updates: Mapping[str, Any] | None = None, run_id: str = "scoped-rebuild") -> RebuildResult:
        """Commit one product to the canonical fixture file without lost writes."""
        with self.aggregation_transaction(run_id=run_id, scope=f"scoped_derived_commit:{product_id}"):
            source_path = output_path if output_path.exists() else input_path
            result = self.rebuild_product_scope(read_state(source_path), product_id, updates=updates, run_id=run_id, lock_already_held=True)
            write_state(output_path, result.state)
            return result

    def rebuild_all_admin_state_file(self, input_path: Path, output_path: Path, *, run_id: str = "admin-full-rebuild") -> RebuildResult:
        """Run the explicit full rebuild under the same fixture transaction."""
        with self.aggregation_transaction(run_id=run_id, scope="admin_full_rebuild"):
            source_path = output_path if output_path.exists() else input_path
            result = self.rebuild_all_admin(read_state(source_path), run_id=run_id, lock_already_held=True)
            write_state(output_path, result.state)
            return result


def read_state(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("state must be a JSON object")
    return value


def write_state(path: Path, state: Mapping[str, Any]) -> None:
    atomic_write_json(path, dict(state))
