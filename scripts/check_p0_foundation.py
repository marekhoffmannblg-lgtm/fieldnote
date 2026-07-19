"""Offline P0 regression checks for coordination, durability and state precedence."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "fieldnote-api"))

from p0_runtime import (  # noqa: E402
    DEFAULT_STAGE_TIMEOUTS,
    FileLock,
    LockUnavailableError,
    atomic_write_bundle,
    atomic_write_json,
)
from run_coordinator import RunCoordinator  # noqa: E402


def load_api():
    spec = importlib.util.spec_from_file_location("fieldnote_api_p0_test", ROOT / "fieldnote-api" / "app.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_manifest(path: Path, payload: dict) -> None:
    atomic_write_json(path, payload, preserve_previous=False)


def main() -> int:
    failures: list[str] = []
    api = load_api()
    with tempfile.TemporaryDirectory(prefix="fieldnote-p0-") as temporary:
        temp = Path(temporary)
        runs = temp / "runs"
        output = temp / "output"
        coordinator = RunCoordinator(runs_root=runs, output_root=output)

        # 1-2. Same product conflicts; two distinct products may run together.
        coordinator.acquire_product(run_id="run-a", product_slug="brand__one", group_key="brand|one")
        try:
            coordinator.acquire_product(run_id="run-b", product_slug="brand__one", group_key="brand|one")
            failures.append("same_product_lock_missing")
        except LockUnavailableError:
            pass
        api.RUN_COORDINATOR = coordinator
        try:
            api.start_pipeline_run(api.ResearchRequest(brand="Brand", model="One"))
            failures.append("same_product_http_409_missing")
        except api.HTTPException as exc:
            if exc.status_code != 409:
                failures.append("same_product_wrong_http_status")
        coordinator.acquire_product(run_id="run-c", product_slug="brand__two", group_key="brand|two")
        coordinator.release_product("run-a")
        coordinator.release_product("run-c")

        context = coordinator.create_context({
            "run_id": "context-run",
            "product_slug": "brand__context",
            "group_key": "brand|context",
            "brand": "Brand",
            "model": "Context",
            "marketplace": "allegro",
            "selected_offer_ids": ["111", "222"],
            "flags": {"resume": True},
        }, source_snapshot_paths=["input/firecrawl_offer_pages/111/technical_clean.md"])
        context_path = runs / "work" / "context-run" / "context.json"
        if (
            not context_path.is_file()
            or context.get("pipeline_version") != "p0-run-coordinator-v1"
            or context.get("selected_offer_ids") != ["111", "222"]
            or context.get("source_snapshot_paths") != ["input/firecrawl_offer_pages/111/technical_clean.md"]
        ):
            failures.append("immutable_run_context_missing")

        aggregation = FileLock(output / "run_locks" / "aggregation.lock", {"run_id": "aggregate-a"})
        aggregation.acquire()
        try:
            FileLock(output / "run_locks" / "aggregation.lock", {"run_id": "aggregate-b"}).acquire()
            failures.append("global_aggregation_lock_missing")
        except LockUnavailableError:
            pass
        aggregation.release()

        # 3. Stage timeout has a central, deterministic limit.
        runner_spec = importlib.util.spec_from_file_location("fieldnote_runner_p0_test", ROOT / "scripts" / "run_model_research_pipeline.py")
        assert runner_spec and runner_spec.loader
        runner = importlib.util.module_from_spec(runner_spec)
        sys.modules[runner_spec.name] = runner
        runner_spec.loader.exec_module(runner)
        previous_timeout = DEFAULT_STAGE_TIMEOUTS["targeted search"]
        DEFAULT_STAGE_TIMEOUTS["targeted search"] = 1
        try:
            runner.run_stage(1, "targeted search", [sys.executable, "-c", "import time; time.sleep(3)"])
            failures.append("subprocess_timeout_missing")
        except RuntimeError as exc:
            if "przekroczył limit" not in str(exc):
                failures.append("subprocess_timeout_message")
        finally:
            DEFAULT_STAGE_TIMEOUTS["targeted search"] = previous_timeout

        # Immutable selection does not rewrite shared targeted-search output.
        shared_offers = temp / "shared_new_offers.csv"
        shared_offers.write_text("external_offer_id,title\n111,One\n222,Two\n", encoding="utf-8")
        run_selection = temp / "run" / "selected_new_offers.csv"
        selected = runner.materialize_selected_offers(shared_offers, run_selection, {"222"})
        if [row.get("external_offer_id") for row in selected] != ["222"] or "111" not in shared_offers.read_text(encoding="utf-8"):
            failures.append("immutable_run_selection_missing")

        # 4. API cancellation stops only the owned child process and persists intent.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"], start_new_session=True)
        api.RUNS_ROOT = runs
        api.RUN_COORDINATOR = coordinator
        cancel_id = str(uuid.uuid4())
        api.save_run({
            "run_id": cancel_id,
            "status": "running",
            "product_slug": "brand__cancel",
            "child_pid": child.pid,
            "logs": [],
        })
        cancelled = api.cancel_run(cancel_id)
        if not cancelled.get("cancel_requested_at"):
            failures.append("cancel_endpoint_missing_intent")
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            failures.append("cancel_did_not_stop_child")

        # 5. Startup recovery turns a stale active manifest into interrupted.
        stale_id = str(uuid.uuid4())
        stale = {
            "run_id": stale_id,
            "status": "running",
            "product_slug": "brand__orphan",
            "child_pid": 999_999_999,
            "logs": [],
        }
        write_manifest(runs / f"{stale_id}.json", stale)
        recovered: list[str] = []
        # Exercise the same recovery entry point that runs at API startup.
        previous_runs_root = api.RUNS_ROOT
        previous_coordinator = api.RUN_COORDINATOR
        previous_product_state_path = api.PRODUCT_STATE_PATH
        previous_legacy_status_path = api.PRODUCT_ANALYSIS_STATUS_PATH
        api.RUNS_ROOT = runs
        api.RUN_COORDINATOR = coordinator
        api.PRODUCT_STATE_PATH = temp / "recovery_product_state.json"
        api.PRODUCT_ANALYSIS_STATUS_PATH = temp / "recovery_legacy_status.json"
        api.recover_interrupted_runs()
        api.RUNS_ROOT = previous_runs_root
        api.RUN_COORDINATOR = previous_coordinator
        api.PRODUCT_STATE_PATH = previous_product_state_path
        api.PRODUCT_ANALYSIS_STATUS_PATH = previous_legacy_status_path
        recovered_payload = json.loads((runs / f"{stale_id}.json").read_text(encoding="utf-8"))
        if recovered_payload.get("status") != "interrupted":
            failures.append("startup_recovery_missing")

        # 6-7. A failed staged bundle must leave the valid group/state unchanged.
        offer_dir = temp / "offer"
        atomic_write_json(offer_dir / "group.json", {"version": "old-group"}, preserve_previous=False)
        atomic_write_json(offer_dir / "model_state.json", {"version": "old-state"}, preserve_previous=False)
        try:
            atomic_write_bundle(
                offer_dir,
                {"group.json": "{broken", "model_state.json": "{also broken"},
                json_files={"group.json", "model_state.json"},
            )
            failures.append("bundle_validation_missing")
        except json.JSONDecodeError:
            pass
        current_group = json.loads((offer_dir / "group.json").read_text(encoding="utf-8"))
        current_state = json.loads((offer_dir / "model_state.json").read_text(encoding="utf-8"))
        if current_group.get("version") != "old-group":
            failures.append("group_previous_result_not_preserved")
        if current_state.get("version") != "old-state":
            failures.append("model_state_previous_result_not_preserved")

        # 8-10. Canonical state always preserves a valid earlier result.
        api.PRODUCT_STATE_PATH = temp / "product_state.json"
        api.PRODUCT_ANALYSIS_STATUS_PATH = temp / "legacy_status.json"
        api.update_product_state("brand__ready", "succeeded", run_id="success-1")
        after_failed = api.update_product_state("brand__ready", "failed", run_id="failed-1", error="fixture failure")
        if api.public_product_status(after_failed) != "refresh_recommended" or after_failed.get("result_status") != "ready":
            failures.append("successful_result_overridden_by_failed_run")
        no_result_failed = api.update_product_state("brand__failed", "failed", run_id="failed-2", error="fixture failure")
        if api.public_product_status(no_result_failed) != "analysis_failed":
            failures.append("failed_without_result_status_wrong")
        active_refresh = api.update_product_state("brand__ready", "running", run_id="refresh-1")
        if api.public_product_status(active_refresh) != "analysis_running":
            failures.append("active_refresh_status_wrong")

    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1
    print("P0 tests: locks=OK timeout=OK cancel=OK recovery=OK atomic_bundle=OK canonical_status=OK")
    print("Result: OK")
    return 0


if __name__ == "__main__":
    api_python = ROOT / "fieldnote-api" / ".venv" / "bin" / "python3"
    if importlib.util.find_spec("fastapi") is None and api_python.is_file() and Path(sys.prefix) != api_python.parent.parent:
        os.execv(str(api_python), [str(api_python), __file__])
    raise SystemExit(main())
