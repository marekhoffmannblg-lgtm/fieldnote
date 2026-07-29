"""Adapter around the legacy CLI used by the durable worker.

It intentionally does not interpret or commit benchmark files.  The existing
pipeline keeps that responsibility while the job payload/usage stays durable.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE = PROJECT_ROOT / "scripts" / "run_model_research_pipeline.py"


@dataclass(frozen=True)
class PipelineResult:
    status: str
    usage: dict[str, Any]
    result: dict[str, Any]
    error: str = ""


class PipelineService:
    def __init__(self, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> None:
        self.runner = runner

    def execute(self, job: dict[str, Any], *, cancel_check_file: Path) -> PipelineResult:
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        limits = payload.get("limits") if isinstance(payload.get("limits"), dict) else {}
        selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
        selected = [str(value) for value in selection.get("selected_offer_ids", []) if str(value).strip()]
        manufacturer = [str(value) for value in selection.get("selected_manufacturer_source_ids", []) if str(value).strip()]
        include_manufacturer = bool(selection.get("include_manufacturer_sources"))
        timeout_seconds = int(limits.get("timeout_seconds", 900) or 900)
        max_pages = int(limits.get("max_pages", 10) or 10)
        # A requested selection is a deterministic upper bound for the legacy
        # offer-page stage. Refuse an over-budget run before invoking any paid
        # adapter instead of running and inventing a post-hoc usage counter.
        if len(selected) > max_pages:
            return PipelineResult(
                status="partial",
                usage={"pages": len(selected), "pages_known": True, "ai_tokens": None, "usage_complete": False},
                result={"reason": "max_pages_exceeded_before_start", "selected_offer_count": len(selected)},
                error="max_pages_exceeded",
            )
        context_path: Path | None = None
        command = [
            sys.executable, str(PIPELINE), "--marketplace", "allegro",
            "--brand", str(payload.get("brand", "")), "--model", str(payload.get("model", "")),
            "--category-key", str(payload.get("category_key", "")),
            "--benchmark-group", str(payload.get("benchmark_group", "")),
            "--apply", "--resume", "--skip-product-profile",
            "--cancel-check-file", str(cancel_check_file),
        ]
        # The context is an immutable, secret-free handoff.  Keep it outside
        # project output and remove it after the child exits.
        context = self._build_run_context(job, selection, selected, manufacturer, include_manufacturer)
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", prefix="fieldnote-run-context-", delete=False, encoding="utf-8") as handle:
                context_path = Path(handle.name)
                json.dump(context, handle, ensure_ascii=False, sort_keys=True)
            command.extend(["--run-context", str(context_path)])
        except OSError as exc:
            return PipelineResult(status="failed", usage={}, result={}, error=f"run_context_error: {exc}")
        if bool(selection.get("skip_ai")):
            command.append("--skip-ai")
        try:
            if self.runner is subprocess.run:
                return self._execute_managed(command, cancel_check_file, timeout_seconds)
            completed = self.runner(command, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            return PipelineResult(status="partial", usage={"pages": len(selected), "pages_known": True, "ai_tokens": None, "timeout": True, "usage_complete": False}, result={"output_tail": str(exc)[-4000:]}, error="pipeline_timeout")
        finally:
            if context_path:
                context_path.unlink(missing_ok=True)
        output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        status = self._status(output, completed.returncode)
        usage = self._usage_from_output(output, selected_count=len(selected), skip_ai=bool(selection.get("skip_ai")))
        usage["command_exit_code"] = completed.returncode
        if usage.get("usage_complete") is False and status == "succeeded":
            status = "partial"
        scoped_commit = self._scoped_commit_from_output(output)
        result = {"output_tail": output[-4000:]}
        if scoped_commit:
            result["scoped_commit"] = scoped_commit
        return PipelineResult(status=status, usage=usage, result=result, error="" if completed.returncode == 0 else output[-800:])

    @staticmethod
    def _build_run_context(job: dict[str, Any], selection: dict[str, Any], selected: list[str], manufacturer: list[str], include_manufacturer: bool) -> dict[str, Any]:
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        brand, model = str(payload.get("brand", "")), str(payload.get("model", ""))
        group_key = f"{' '.join(brand.lower().split())}|{' '.join(model.lower().split())}"
        return {
            "schema_version": "1",
            "run_id": str(job.get("job_id", "")),
            "pipeline_version": "durable-worker-unit5",
            "marketplace": "allegro",
            "brand": brand,
            "model": model,
            "group_key": group_key,
            "selected_offer_ids": selected,
            "selected_manufacturer_source_ids": manufacturer,
            "include_manufacturer_sources": include_manufacturer,
            "selected_offers_csv": str(selection.get("selected_offers_csv", "")),
            "product_scope": selection.get("product_scope") if isinstance(selection.get("product_scope"), dict) else {
                "product_id": str(payload.get("product_id", job.get("product_id", ""))),
                "product_slug": str(payload.get("product_slug", "")),
                "group_key": group_key,
            },
            "benchmark_group_scope": selection.get("benchmark_group_scope") if isinstance(selection.get("benchmark_group_scope"), dict) else {
                "category_key": str(payload.get("category_key", "")),
                "benchmark_group": str(payload.get("benchmark_group", "")),
            },
        }

    @staticmethod
    def _scoped_commit_from_output(output: str) -> dict[str, Any]:
        for line in reversed(output.splitlines()):
            key, separator, raw = line.partition("=")
            if key != "scoped_commit" or not separator:
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            if isinstance(value, dict) and isinstance(value.get("scope"), dict) and isinstance(value.get("semantic_state"), dict):
                return value
        return {}

    @staticmethod
    def _usage_from_output(output: str, *, selected_count: int, skip_ai: bool) -> dict[str, Any]:
        # Legacy CLI currently emits no provider token/cost telemetry. Pages
        # are known only as the explicit selected offer count; unknown metrics
        # stay null so a successful child cannot claim fabricated zero usage.
        usage: dict[str, Any] = {"pages": selected_count, "pages_known": True, "ai_tokens": 0 if skip_ai else None, "ai_tokens_known": skip_ai, "usage_complete": skip_ai}
        for line in output.splitlines():
            key, sep, raw = line.partition("=")
            if not sep or key.strip() not in {"pages", "ai_tokens", "cost_used"}:
                continue
            try:
                usage[key.strip()] = max(0, int(raw.strip())) if key.strip() != "cost_used" else max(0.0, float(raw.strip()))
                usage[f"{key.strip()}_known"] = True
            except ValueError:
                continue
        usage["usage_complete"] = bool(usage.get("pages_known") and usage.get("ai_tokens_known"))
        return usage

    @staticmethod
    def _execute_managed(command: list[str], cancel_check_file: Path, timeout_seconds: int) -> PipelineResult:
        process = subprocess.Popen(command, cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if PipelineService._cancel_requested(cancel_check_file):
                    PipelineService._terminate_process_group(process)
                    stdout, stderr = process.communicate()
                    return PipelineResult("cancelled", {"usage_complete": False}, {"output_tail": f"{stdout or ''}\n{stderr or ''}"[-4000:]}, "pipeline_cancelled")
                if time.monotonic() - started >= timeout_seconds:
                    PipelineService._terminate_process_group(process)
                    stdout, stderr = process.communicate()
                    return PipelineResult("partial", {"timeout": True, "usage_complete": False}, {"output_tail": f"{stdout or ''}\n{stderr or ''}"[-4000:]}, "pipeline_timeout")
                time.sleep(0.1)
            stdout, stderr = process.communicate()
        finally:
            if process.poll() is None:
                PipelineService._terminate_process_group(process)
        output = f"{stdout or ''}\n{stderr or ''}"
        status = PipelineService._status(output, process.returncode)
        usage = PipelineService._usage_from_output(output, selected_count=0, skip_ai=False)
        if usage.get("usage_complete") is False and status == "succeeded":
            status = "partial"
        result = {"output_tail": output[-4000:]}
        scoped_commit = PipelineService._scoped_commit_from_output(output)
        if scoped_commit:
            result["scoped_commit"] = scoped_commit
        return PipelineResult(status, usage, result, "" if process.returncode == 0 else output[-800:])

    @staticmethod
    def _cancel_requested(path: Path) -> bool:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return bool(value.get("cancel_requested"))
        except (OSError, json.JSONDecodeError, AttributeError):
            return False

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()

    @staticmethod
    def _status(output: str, returncode: int) -> str:
        for line in reversed(output.splitlines()):
            if line.startswith("pipeline_status="):
                value = line.partition("=")[2].strip().lower()
                if value in {"success", "partial", "failed"}:
                    return {"success": "succeeded", "partial": "partial", "failed": "failed"}[value]
        return "succeeded" if returncode == 0 else "failed"
