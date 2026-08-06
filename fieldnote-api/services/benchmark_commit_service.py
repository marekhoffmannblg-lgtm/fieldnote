"""Build a bounded durable semantic-commit envelope for one research job."""

from __future__ import annotations

from typing import Any, Mapping

from services.benchmark_rebuild_service import semantic_hash


class BenchmarkCommitError(RuntimeError):
    pass


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _price(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _configuration_scope_id(benchmark_group: str, configuration: str) -> str:
    """Partition durable benchmark history by the model+configuration unit."""
    return f"{benchmark_group}::{configuration}" if configuration else benchmark_group


class BenchmarkCommitService:
    """Translate the secret-free pipeline envelope into one server-side RPC."""

    def __init__(self, jobs: Any) -> None:
        self.jobs = jobs

    def complete(self, job: Mapping[str, Any], lease_token: str, status: str, result: Mapping[str, Any], usage: Mapping[str, Any], cost_used: float) -> dict[str, Any]:
        scoped = _mapping(result.get("scoped_commit"))
        # A bounded run can stop before any derived artefact exists (for
        # example a page-limit preflight or a worker timeout).  It is still a
        # valid partial terminal state and must be fenced/recorded without a
        # semantic snapshot.  Use the job's product identity as the minimal
        # scope required by the server-side RPC.
        if status == "partial" and not scoped:
            product_id = str(job.get("product_id", "")).strip()
            if not product_id:
                raise BenchmarkCommitError("Partial completion requires a product_id.")
            complete = getattr(self.jobs, "complete_incremental", None)
            if not callable(complete):
                raise BenchmarkCommitError("Durable incremental completion RPC is unavailable.")
            return complete(
                str(job.get("job_id", "")),
                lease_token,
                status,
                dict(result),
                dict(usage),
                cost_used,
                {"product_id": product_id, "scope_version": "1", "no_mutation": True},
                [],
            )
        if status == "succeeded" and not scoped:
            raise BenchmarkCommitError("Pipeline did not return a scoped semantic commit envelope.")
        snapshots, scope = self._snapshots(job, scoped)
        complete = getattr(self.jobs, "complete_incremental", None)
        if not callable(complete):
            raise BenchmarkCommitError("Durable incremental completion RPC is unavailable.")
        return complete(
            str(job.get("job_id", "")),
            lease_token,
            status,
            dict(result),
            dict(usage),
            cost_used,
            scope,
            snapshots,
        )

    @staticmethod
    def _snapshots(job: Mapping[str, Any], scoped: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        scope = _mapping(scoped.get("scope"))
        product_id = str(scope.get("product_id") or job.get("product_id") or "").strip()
        group_key = str(scope.get("group_key", "")).strip()
        benchmark_group = str(scope.get("benchmark_group", "")).strip()
        configuration = str(scope.get("configuration", "")).strip()
        if not product_id or not group_key:
            raise BenchmarkCommitError("Scoped commit requires product_id and group_key.")
        state = _mapping(scoped.get("semantic_state"))
        if not state:
            raise BenchmarkCommitError("Scoped commit has no semantic domain state.")
        semantic_benchmark = _mapping(state.get("semantic_benchmark"))
        if not configuration:
            configuration = str(semantic_benchmark.get("configuration", "")).strip()
        participant_ids = [
            str(value).strip()
            for value in scope.get("participant_product_ids", semantic_benchmark.get("participant_product_ids", []))
            if str(value).strip()
        ]
        price = _price(scoped.get("price_median"))
        product_domain = {key: value for key, value in state.items() if key != "price_median"}
        product_scope = {"product_id": product_id, "group_key": group_key}
        if configuration:
            product_scope["configuration"] = configuration
        if participant_ids:
            product_scope["participant_product_ids"] = participant_ids
        product_payload = {"scope": product_scope, "state": state}
        snapshots = [{
            "scope_type": "product",
            "scope_id": product_id,
            "semantic_hash": semantic_hash(product_payload),
            "domain_hash": semantic_hash(product_domain),
            "price_median": price,
            "payload": product_payload,
        }]
        if benchmark_group:
            # A product semantic envelope is not an internal benchmark
            # projection.  Falling back to ``state`` here would make a
            # product-only price_median look like a group-domain change and
            # create a misleading benchmark_group snapshot.  The pipeline may
            # provide an explicit internal projection; otherwise there is no
            # group snapshot to persist for this bounded commit.
            internal = state.get("semantic_benchmark", state.get("internal_benchmark", state.get("internal_benchmarks")))
            if isinstance(internal, Mapping):
                internal_projection: Any = dict(internal)
            elif isinstance(internal, list):
                internal_projection = [dict(item) for item in internal if isinstance(item, Mapping)]
            else:
                internal_projection = None
            if internal_projection:
                group_scope = {"group_key": group_key, "benchmark_group": benchmark_group}
                if configuration:
                    group_scope["configuration"] = configuration
                if participant_ids:
                    group_scope["participant_product_ids"] = participant_ids
                group_payload = {"scope": group_scope, "state": internal_projection}
                snapshots.append({
                    "scope_type": "benchmark_group",
                    "scope_id": _configuration_scope_id(benchmark_group, configuration),
                    "semantic_hash": semantic_hash(group_payload),
                    "domain_hash": semantic_hash(group_payload),
                    "price_median": None,
                    "payload": group_payload,
                })
        for benchmark_id in scoped.get("competitive_benchmark_ids", []):
            benchmark_id = str(benchmark_id).strip()
            if not benchmark_id:
                continue
            payload = {"scope": {"benchmark_id": benchmark_id, "product_id": product_id}, "state": state.get("competitive_benchmarks", [])}
            snapshots.append({
                "scope_type": "competitive_benchmark",
                "scope_id": benchmark_id,
                "semantic_hash": semantic_hash(payload),
                "domain_hash": semantic_hash(payload),
                "price_median": None,
                "payload": payload,
            })
        if len(snapshots) > 16:
            raise BenchmarkCommitError("Scoped commit exceeds snapshot limit.")
        result_scope: dict[str, Any] = {
            "product_id": product_id,
            "group_key": group_key,
            "benchmark_group": benchmark_group,
            "scope_version": "1",
        }
        if configuration:
            result_scope["configuration"] = configuration
        if participant_ids:
            result_scope["participant_product_ids"] = participant_ids
        return snapshots, result_scope
