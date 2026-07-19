from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

from services.integrations import pipeline_environment


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE = PROJECT_ROOT / "scripts" / "run_model_research_pipeline.py"


def parse_result(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    allowed = {"pipeline_status", "mode", "group_key", "cards_found", "unique_offer_ids", "accepted_model_offers", "rejected_other_models", "already_known", "new_offers", "offers_requested", "offers_fetched", "offers_failed", "offers_skipped", "sources_total", "coverage_before", "coverage_after", "coverage_percent", "coverage_change", "targeted_search_recommended", "error", "error_stage"}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key.strip() in allowed:
            result[key.strip()] = value.strip()
    return result


def pipeline_command(brand: str, model: str, mode: str, skip_ai: bool = False) -> list[str]:
    command = [sys.executable, str(PIPELINE), "--marketplace", "allegro", "--brand", brand, "--model", model, "--resume"]
    if mode == "apply":
        command.append("--apply")
    if skip_ai:
        command.append("--skip-ai")
    return command


def run_pipeline(brand: str, model: str, mode: str, skip_ai: bool = False) -> Iterator[tuple[str, list[str], dict[str, str] | None]]:
    """Yield user-safe progress while keeping secrets in the subprocess environment only."""
    lines: list[str] = []
    try:
        process = subprocess.Popen(pipeline_command(brand, model, mode, skip_ai), cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=pipeline_environment(), shell=False, bufsize=1)
    except OSError as exc:
        yield "Nie udało się rozpocząć procesu.", [f"Uruchomienie procesu nie powiodło się: {exc.__class__.__name__}"], {"pipeline_status": "failed", "error": "Nie udało się rozpocząć procesu."}
        return
    if process.stdout:
        for line in process.stdout:
            clean = line.rstrip()
            lines.append(clean)
            if clean.startswith("[") and "/9]" in clean:
                yield clean.split("]", 1)[-1].strip() or "Trwa przygotowanie danych…", lines, None
    return_code = process.wait()
    result = parse_result(lines)
    if return_code and not result.get("pipeline_status"):
        result = {"pipeline_status": "failed", "error": "Proces zatrzymał się przed zakończeniem."}
    yield "Proces zakończony.", lines, result

