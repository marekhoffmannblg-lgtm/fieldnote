"""PostgreSQL-backed research worker. Run as a separate Render worker process."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

from repositories.job_repository import JobRepository
from repositories.supabase_client import SupabaseClient
from services.job_service import cost_number
from services.pipeline_service import PipelineResult, PipelineService
from services.benchmark_commit_service import BenchmarkCommitService


class ResearchWorker:
    def __init__(self, jobs: JobRepository, pipeline: PipelineService, *, worker_id: str | None = None, lease_seconds: int = 60, committer: BenchmarkCommitService | None = None) -> None:
        self.jobs, self.pipeline = jobs, pipeline
        self.worker_id = worker_id or f"worker-{uuid.uuid4()}"
        self.lease_seconds = max(10, lease_seconds)
        self.committer = committer or (BenchmarkCommitService(jobs) if callable(getattr(jobs, "complete_incremental", None)) else None)

    def process_one(self) -> bool:
        job = self.jobs.claim(self.worker_id, self.lease_seconds, max_active=2)
        if not job:
            return False
        token = str(job.get("lease_token", ""))
        if not token:
            return False
        started = self.jobs.start(str(job["job_id"]), token)
        return bool(started) and self._run(started, token)

    def _run(self, job: dict, token: str) -> bool:
        job_id = str(job["job_id"])
        stop_heartbeat, lease_lost = threading.Event(), threading.Event()
        control = Path(tempfile.mkstemp(prefix="fieldnote-job-control-", suffix=".json")[1])

        def heartbeat() -> None:
            interval = max(1, self.lease_seconds // 3)
            while not stop_heartbeat.wait(interval):
                current = self.jobs.heartbeat(job_id, token, self.lease_seconds)
                if not current:
                    lease_lost.set(); self._write_control(control, True); return
                self._write_control(control, bool(current.get("cancel_requested_at")))

        self._write_control(control, bool(job.get("cancel_requested_at")))
        thread = threading.Thread(target=heartbeat, name=f"heartbeat-{job_id}", daemon=True); thread.start()
        try:
            result = PipelineResult("cancelled", {}, {"reason": "cancel_requested_before_start"}) if job.get("cancel_requested_at") else self.pipeline.execute(job, cancel_check_file=control)
            if lease_lost.is_set():
                return False
            final = self._final_status(job, result)
            if self.committer and final in {"succeeded", "partial"}:
                try:
                    completed = self.committer.complete(job, token, final, result.result, result.usage, cost_number(result.usage.get("cost_used", 0)))
                except Exception as exc:
                    failed = {**result.result, "incremental_commit_error": str(exc)}
                    return bool(self.jobs.complete(job_id, token, "failed", failed, result.usage, cost_number(result.usage.get("cost_used", 0))))
                return bool(completed)
            return bool(self.jobs.complete(job_id, token, final, result.result, result.usage, cost_number(result.usage.get("cost_used", 0))))
        finally:
            stop_heartbeat.set(); thread.join(timeout=2); control.unlink(missing_ok=True)

    @staticmethod
    def _write_control(path: Path, cancelled: bool) -> None:
        path.write_text(json.dumps({"cancel_requested": cancelled}), encoding="utf-8")

    @staticmethod
    def _final_status(job: dict, result: PipelineResult) -> str:
        if result.status == "cancelled":
            return "cancelled"
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        limits = payload.get("limits") if isinstance(payload.get("limits"), dict) else {}
        usage = result.usage
        pages = usage.get("pages")
        tokens = usage.get("ai_tokens")
        exceeded = (pages is not None and int(pages) > int(limits.get("max_pages", 10))) or (tokens is not None and int(tokens) > int(limits.get("max_ai_tokens", 20_000))) or (job.get("cost_limit") is not None and usage.get("cost_used") is not None and cost_number(usage.get("cost_used")) > cost_number(job.get("cost_limit")))
        if usage.get("usage_complete") is False and result.status == "succeeded":
            return "partial"
        return "partial" if exceeded else result.status if result.status in {"partial", "succeeded", "failed"} else "failed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FIELDNOTE durable research worker")
    parser.add_argument("--once", action="store_true"); parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args(argv)
    worker = ResearchWorker(JobRepository(SupabaseClient.from_env()), PipelineService(), lease_seconds=int(os.getenv("FIELDNOTE_JOB_LEASE_SECONDS", "60")))
    while True:
        worked = worker.process_one()
        if args.once: return 0
        if not worked: time.sleep(max(0.2, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
