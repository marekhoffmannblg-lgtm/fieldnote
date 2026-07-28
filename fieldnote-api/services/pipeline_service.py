"""Adapter around the legacy CLI used by the durable worker.

It intentionally does not interpret or commit benchmark files.  The existing
pipeline keeps that responsibility while the job payload/usage stays durable.
"""

from __future__ import annotations

import json
import subprocess
import sys
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
        command = [
            sys.executable, str(PIPELINE), "--marketplace", "allegro",
            "--brand", str(payload.get("brand", "")), "--model", str(payload.get("model", "")),
            "--category-key", str(payload.get("category_key", "")),
            "--benchmark-group", str(payload.get("benchmark_group", "")),
            "--apply", "--resume", "--skip-product-profile",
            "--cancel-check-file", str(cancel_check_file),
        ]
        if bool(selection.get("skip_ai")):
            command.append("--skip-ai")
        selected = selection.get("selected_offer_ids")
        # The legacy CLI receives offer selection through the existing immutable
        # context only; Unit 5 never fabricates a second local source of truth.
        try:
            completed = self.runner(command, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=int(limits.get("timeout_seconds", 900)), check=False)
        except subprocess.TimeoutExpired as exc:
            return PipelineResult(status="partial", usage={"pages": 0, "ai_tokens": 0, "timeout": True}, result={"output_tail": str(exc)[-4000:]}, error="pipeline_timeout")
        output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        status = self._status(output, completed.returncode)
        usage = {"pages": len(selected) if isinstance(selected, list) else 0, "ai_tokens": 0, "command_exit_code": completed.returncode}
        return PipelineResult(status=status, usage=usage, result={"output_tail": output[-4000:]}, error="" if completed.returncode == 0 else output[-800:])

    @staticmethod
    def _status(output: str, returncode: int) -> str:
        for line in reversed(output.splitlines()):
            if line.startswith("pipeline_status="):
                value = line.partition("=")[2].strip().lower()
                if value in {"success", "partial", "failed"}:
                    return {"success": "succeeded", "partial": "partial", "failed": "failed"}[value]
        return "succeeded" if returncode == 0 else "failed"
