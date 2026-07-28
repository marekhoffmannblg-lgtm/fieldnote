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


class ResearchWorker:
    def __init__(self, jobs: JobRepository, pipeline: PipelineService, *, worker_id: str | None = None, lease_seconds: int = 60) -> None:
        self.jobs, self.pipeline = jobs, pipeline
        self.worker_id = worker_id or f"worker-{uuid.uuid4()}"
        self.lease_seconds = max(10, lease_seconds)

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
        alive, lease_lost = threading.Event(), threading.Event(); alive.set()
        control = Path(tempfile.mkstemp(prefix="fieldnote-job-control-", suffix=".json")[1])

        def heartbeat() -> None:
            while alive.wait(max(1, self.lease_seconds // 3)) is False:
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
            return bool(self.jobs.complete(job_id, token, final, result.result, result.usage, cost_number(result.usage.get("cost_used", 0))))
        finally:
            alive.clear(); thread.join(timeout=2); control.unlink(missing_ok=True)

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
        exceeded = (int(usage.get("pages", 0) or 0) > int(limits.get("max_pages", 10)) or int(usage.get("ai_tokens", 0) or 0) > int(limits.get("max_ai_tokens", 20_000)) or (job.get("cost_limit") is not None and cost_number(usage.get("cost_used", 0)) > cost_number(job.get("cost_limit"))))
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
