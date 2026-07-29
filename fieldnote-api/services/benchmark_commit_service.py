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
        if not product_id or not group_key:
            raise BenchmarkCommitError("Scoped commit requires product_id and group_key.")
        state = _mapping(scoped.get("semantic_state"))
        if not state:
            raise BenchmarkCommitError("Scoped commit has no semantic domain state.")
        price = _price(scoped.get("price_median"))
        product_domain = {key: value for key, value in state.items() if key != "price_median"}
        product_payload = {"scope": {"product_id": product_id, "group_key": group_key}, "state": state}
        snapshots = [{
            "scope_type": "product",
            "scope_id": product_id,
            "semantic_hash": semantic_hash(product_payload),
            "domain_hash": semantic_hash(product_domain),
            "price_median": price,
            "payload": product_payload,
        }]
        if benchmark_group:
            group_payload = {"scope": {"group_key": group_key, "benchmark_group": benchmark_group}, "state": state.get("internal_benchmark", state)}
            snapshots.append({
                "scope_type": "benchmark_group",
                "scope_id": benchmark_group,
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
        return snapshots, {"product_id": product_id, "group_key": group_key, "benchmark_group": benchmark_group, "scope_version": "1"}
