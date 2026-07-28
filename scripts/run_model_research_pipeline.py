from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from firecrawl_offer_export import export_firecrawl_offer_urls
from prepare_firecrawl_offer_queue import QUEUE_COLUMNS, prepare_queue
from catalog_registry import ensure_catalog_product, ensure_group_directory, product_for_group_key
from category_registry import CategoryValidationError, validate_category_assignment
from run_context import RunCancelledError, raise_if_cancelled
from p0_runtime import (
    FileLock,
    LockUnavailableError,
    atomic_write_csv,
    atomic_write_json,
    stage_timeout,
)


def normalized(value: str) -> str:
    return " ".join(value.lower().split())


def path_slug(value: str) -> str:
    import re
    import unicodedata

    normalized_value = unicodedata.normalize("NFKD", value)
    normalized_value = "".join(char for char in normalized_value if not unicodedata.combining(char))
    normalized_value = normalized_value.replace("ł", "l").replace("Ł", "l")
    return re.sub(r"[^a-z0-9]+", "-", normalized_value.lower()).strip("-")


def read_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def output_counter(output: str, key: str) -> int:
    """Read one integer emitted by a scoped maintenance script."""
    for line in output.splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == key:
            try:
                return int(value.strip())
            except ValueError:
                return 0
    return 0


def queue_rows_for_offer_ids(offer_ids: set[str]) -> list[dict[str, str]]:
    if not offer_ids:
        return []
    return [row for row in read_csv(ROOT / "output" / "firecrawl_offer_queue.csv") if row.get("offer_id", "") in offer_ids]


def offer_ids_with_status(offer_ids: set[str], status: str) -> set[str]:
    return {
        row.get("offer_id", "")
        for row in queue_rows_for_offer_ids(offer_ids)
        if row.get("status", "").lower() == status and row.get("offer_id", "")
    }


def retry_offer_ids_for_model(marketplace: str, brand: str, model: str) -> set[str]:
    """Retry only failures belonging to the current model, never the entire queue."""
    target_brand = normalized(brand)
    target_model = normalized(model)
    result: set[str] = set()
    for row in read_csv(ROOT / "output" / "firecrawl_offer_queue.csv"):
        if row.get("status", "").lower() != "error":
            continue
        if normalized(row.get("brand", "")) != target_brand:
            continue
        if normalized(row.get("detected_model", "")) != target_model:
            continue
        try:
            retries = int(row.get("retry_count", "0") or 0)
        except ValueError:
            retries = 0
        if retries < 3 and row.get("offer_id", ""):
            result.add(row["offer_id"])
    return result


def write_run_context(context: dict[str, object]) -> Path:
    """Create a temporary, secret-free handoff for the incremental pipeline stages."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", prefix="benchmark-run-", encoding="utf-8", delete=False) as handle:
        path = Path(handle.name)
    atomic_write_json(path, context, preserve_previous=False)
    return path


def load_run_context(path: str | None) -> dict[str, object]:
    if not path:
        return {}
    value = read_json(Path(path), {})
    if not isinstance(value, dict) or not value.get("run_id"):
        raise RuntimeError("Nieprawidłowy immutable run context.")
    return value


REQUIRED_OFFER_SNAPSHOTS = (
    "markdown.md",
    "html.html",
    "raw_response.json",
    "technical_clean.md",
    "offer_sections.json",
)


def offer_snapshot_complete(offer_id: str, offer_pages_root: Path | None = None) -> bool:
    """A fetched source is reusable only when downstream artifacts are present."""
    base = (offer_pages_root or ROOT / "input" / "firecrawl_offer_pages") / offer_id
    return bool(offer_id) and all((base / name).is_file() for name in REQUIRED_OFFER_SNAPSHOTS)


def materialize_selected_offers(
    source_path: Path,
    destination_path: Path,
    selected_offer_ids: set[str],
    *,
    queue_path: Path | None = None,
    offer_pages_root: Path | None = None,
) -> list[dict[str, str]]:
    """Materialize exactly the UI selection, including known offers.

    `candidate_offers.csv` deliberately excludes already known records, so it
    cannot be the source of truth for an owned run. The full extracted listing
    is filtered by immutable `selected_offer_ids`; each selected source is
    either reused from complete local artifacts or scheduled for one fetch.
    """
    if not source_path.exists():
        return []
    with source_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    queue_by_offer_id = {
        str(row.get("offer_id", "")).strip(): row
        for row in read_csv(queue_path or ROOT / "output" / "firecrawl_offer_queue.csv")
        if str(row.get("offer_id", "")).strip()
    }
    selected: list[dict[str, str]] = []
    for row in rows:
        offer_id = str(row.get("offer_id", row.get("external_offer_id", ""))).strip()
        if offer_id not in selected_offer_ids:
            continue
        item = dict(row)
        item["external_offer_id"] = offer_id
        queue_row = queue_by_offer_id.get(offer_id, {})
        item["owned_run_status"] = "reused" if offer_snapshot_complete(offer_id, offer_pages_root) else "fetch"
        item["queue_status_before"] = str(queue_row.get("status", ""))
        selected.append(item)
    output_fields = list(dict.fromkeys([*fields, "external_offer_id", "owned_run_status", "queue_status_before"]))
    atomic_write_csv(destination_path, output_fields, selected, preserve_previous=False)
    return selected


def prepare_selected_offer_queue(offer_ids: set[str], queue_path: Path | None = None) -> set[str]:
    """Schedule only explicitly selected existing rows for one normal fetch."""
    if not offer_ids:
        return set()
    path = queue_path or ROOT / "output" / "firecrawl_offer_queue.csv"
    rows = read_csv(path)
    existing: set[str] = set()
    changed = False
    for row in rows:
        offer_id = str(row.get("offer_id", "")).strip()
        if offer_id not in offer_ids:
            continue
        existing.add(offer_id)
        if row.get("status", "").lower() != "pending":
            row["status"] = "pending"
            changed = True
    if changed:
        atomic_write_csv(path, QUEUE_COLUMNS, rows)
    return existing


def run_stage(
    number: int,
    label: str,
    command: list[str] | None,
    detail: str = "",
    allow_failure: bool = False,
    history: ResearchRun | None = None,
) -> tuple[str, int]:
    # Durable worker mirrors its PostgreSQL cancellation flag to this temporary
    # control file. Checks occur before stages and before their commit-capable
    # child commands, while legacy CLI calls omit the option entirely.
    raise_if_cancelled(getattr(run_stage, "cancel_check_file", None))
    suffix = f" ({detail})" if detail else ""
    print(f"[{number}/9] {label}{suffix}", flush=True)
    record = history.start_stage(number, label) if history else None
    if command is None:
        if history and record:
            history.finish_stage(record, "skipped", detail or "skipped")
        return "", 0
    try:
        lock: FileLock | None = None
        if number in {8, 9}:
            lock = FileLock(ROOT / "output" / "run_locks" / "aggregation.lock", {"run_id": getattr(history, "run_id", "cli"), "scope": "global_aggregation"})
            lock.acquire()
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=stage_timeout(label),
            )
        finally:
            if lock:
                lock.release()
    except subprocess.TimeoutExpired as exc:
        if history and record:
            history.finish_stage(record, "timed_out", f"timeout after {stage_timeout(label)}s")
        raise RuntimeError(f"Etap {number}/9 przekroczył limit {stage_timeout(label)} sekund: {label}") from exc
    except LockUnavailableError as exc:
        if history and record:
            history.finish_stage(record, "failed", exc)
        raise RuntimeError(f"Etap {number}/9 nie uzyskał globalnej blokady: {label}") from exc
    except OSError as exc:
        if history and record:
            history.finish_stage(record, "failed", exc)
        raise
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr, flush=True)
    if history and record:
        status = "success" if result.returncode == 0 else "failed"
        history.finish_stage(record, status, detail or ("completed" if result.returncode == 0 else f"exit code {result.returncode}"))
    if result.returncode and not allow_failure:
        raise RuntimeError(f"Etap {number}/9 nie powiódł się: {label}")
    raise_if_cancelled(getattr(run_stage, "cancel_check_file", None))
    return result.stdout, result.returncode


def add_new_offers_to_queue(new_rows: list[dict[str, str]], brand: str, model: str) -> set[str]:
    """Reuse the existing Firecrawl export and queue preparation helpers."""
    export_rows = [
        {
            "offer_id": row.get("external_offer_id", ""),
            "normalized_url": row.get("canonical_url", ""),
            "title": row.get("title", ""),
            "detected_model": model,
        }
        for row in new_rows
    ]
    export_firecrawl_offer_urls(
        export_rows,
        output_path=ROOT / "output" / "firecrawl_offer_urls.csv",
        export_reason="targeted_model_research",
        detected_model=model,
        brand=brand,
        category="Wózki",
    )
    prepare_queue()
    return {row.get("external_offer_id", "") for row in new_rows if row.get("external_offer_id", "")}


def move_queue_rows_first(offer_ids: set[str]) -> int:
    """Keep the existing fetcher scoped to the just-added targeted offers."""
    queue_path = ROOT / "output" / "firecrawl_offer_queue.csv"
    rows = read_csv(queue_path)
    selected = [row for row in rows if row.get("offer_id") in offer_ids and row.get("status") == "pending"]
    if not selected:
        return 0
    remaining = [row for row in rows if row not in selected]
    atomic_write_csv(queue_path, QUEUE_COLUMNS, selected + remaining)
    return len(selected)


def group_has_unprocessed_sources(group_key: str) -> bool:
    groups = ROOT / "output" / "model_groups"
    for group_path in groups.glob("*/group.json"):
        group = read_json(group_path, {})
        if not isinstance(group, dict) or group.get("group_key") != group_key:
            continue
        state = read_json(group_path.parent / "model_state.json", {})
        processed = set(state.get("processed_source_ids", [])) if isinstance(state, dict) else set()
        sources = group.get("sources", group.get("offers", []))
        for source in sources if isinstance(sources, list) else []:
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_id") or f"{source.get('marketplace', 'allegro')}:{source.get('offer_id', source.get('external_offer_id', ''))}"
            if source_id and source_id not in processed:
                return True
        return False
    raise RuntimeError(f"Nie znaleziono grupy modelu: {group_key}")


def coverage_for_group(group_key: str) -> dict[str, object]:
    rows = read_json(ROOT / "output" / "model_coverage.json", [])
    if isinstance(rows, list):
        return next((row for row in rows if isinstance(row, dict) and row.get("group_key") == group_key), {})
    return {}


def is_controlled_source_analysis_failure(returncode: int, output: str) -> bool:
    """Recognize the cascade's safe per-source failure without parsing tracebacks."""
    return returncode == SOURCE_ANALYSIS_PROVIDER_ERROR_EXIT and "source_analysis_status=failed" in output


def controlled_source_analysis_message(output: str) -> str:
    if "source_analysis_error_code=source_analysis_timeout" in output:
        return "Analiza źródła przekroczyła limit czasu. Zachowano dotychczasowe dane."
    return "Analiza źródła nie powiodła się. Zachowano dotychczasowe dane."


FETCH_KEYS = ("fetch_status", "offers_requested", "offers_fetched", "offers_failed", "offers_skipped")
SOURCE_ANALYSIS_PROVIDER_ERROR_EXIT = 20
FIXTURE_SCENARIOS = ("success", "partial", "failed", "empty_results")
MAX_RESEARCH_RUNS = 500
PREVIEW_KEYS = (
    "cards_found",
    "unique_offer_ids",
    "accepted_model_offers",
    "rejected_other_models",
    "already_known",
    "new_offers",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def numeric(value: object) -> float:
    try:
        return float(str(value or 0).replace(",", "."))
    except ValueError:
        return 0.0


def boolean(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "tak"}


def safe_text(value: object) -> str:
    """Keep operational history useful without persisting credentials or long technical output."""
    import re

    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"(?i)(firecrawl_api_key|openai_api_key|authorization)\s*[:=]\s*\S+", r"\1=[redacted]", text)
    text = re.sub(r"(?i)bearer\s+[a-z0-9._-]+", "Bearer [redacted]", text)
    return text[:500]


class ResearchRun:
    """Small append-only manifest for one pipeline invocation."""

    def __init__(self, root: Path, args: argparse.Namespace, group_key: str, mode: str) -> None:
        self.root = root
        self.args = args
        self.group_key = group_key
        self.started_at = utc_now()
        self.started_clock = time.monotonic()
        self.run_id = f"{self.started_at.replace(':', '').replace('-', '').replace('Z', '')}-{uuid.uuid4().hex[:8]}"
        self.payload: dict[str, object] = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": "",
            "duration_seconds": 0.0,
            "marketplace": normalized(args.marketplace),
            "brand": args.brand,
            "model": args.model,
            "group_key": group_key,
            "mode": mode,
            "pipeline_status": "failed",
            "stages": [],
            "cards_found": 0,
            "unique_offer_ids": 0,
            "accepted_model_offers": 0,
            "new_offers": 0,
            "offers_requested": 0,
            "offers_fetched": 0,
            "offers_failed": 0,
            "offers_skipped": 0,
            "offers_in_run": 0,
            "offers_cleaned": 0,
            "registry_records_updated": 0,
            "groups_updated": 0,
            "sources_total": 0,
            "coverage_before": 0.0,
            "coverage_after": 0.0,
            "coverage_change": 0.0,
            "targeted_search_recommended": False,
            "error_stage": "",
            "error_message": "",
        }

    def start_stage(self, number: int, name: str) -> dict[str, object]:
        record: dict[str, object] = {
            "number": number,
            "name": name,
            "status": "running",
            "started_at": utc_now(),
            "finished_at": "",
            "duration_seconds": 0.0,
            "summary": "",
            "_started_clock": time.monotonic(),
        }
        stages = self.payload["stages"]
        if isinstance(stages, list):
            stages.append(record)
        return record

    def finish_stage(self, record: dict[str, object], status: str, summary: object = "") -> None:
        record["status"] = status
        record["finished_at"] = utc_now()
        record["duration_seconds"] = round(time.monotonic() - float(record.pop("_started_clock", time.monotonic())), 3)
        record["summary"] = safe_text(summary)

    def update_latest_stage(self, status: str, summary: object) -> None:
        stages = self.payload.get("stages", [])
        if not isinstance(stages, list) or not stages:
            return
        record = stages[-1]
        if isinstance(record, dict):
            record["status"] = status
            record["summary"] = safe_text(summary)

    def complete(self, pipeline_status: str, *, error_stage: str = "", error_message: object = "") -> None:
        self.payload["pipeline_status"] = pipeline_status
        self.payload["finished_at"] = utc_now()
        self.payload["duration_seconds"] = round(time.monotonic() - self.started_clock, 3)
        self.payload["error_stage"] = error_stage
        self.payload["error_message"] = safe_text(error_message)

    def update_summary(
        self,
        preview: dict[str, str] | None = None,
        fetch: dict[str, str] | None = None,
        coverage_before: dict[str, object] | None = None,
        coverage_after: dict[str, object] | None = None,
        new_offers: int = 0,
        offers_in_run: int = 0,
        offers_cleaned: int = 0,
        registry_records_updated: int = 0,
        groups_updated: int = 0,
    ) -> None:
        preview = preview or {}
        fetch = fetch or {}
        coverage_before = coverage_before or {}
        coverage_after = coverage_after or {}
        for key in ("cards_found", "unique_offer_ids", "accepted_model_offers", "new_offers"):
            source = preview.get(key, new_offers if key == "new_offers" else 0)
            self.payload[key] = int(numeric(source))
        self.payload["new_offers"] = new_offers
        self.payload["offers_in_run"] = offers_in_run
        self.payload["offers_cleaned"] = offers_cleaned
        self.payload["registry_records_updated"] = registry_records_updated
        self.payload["groups_updated"] = groups_updated
        for key in FETCH_KEYS[1:]:
            self.payload[key] = int(numeric(fetch.get(key, 0)))
        before_value = numeric(coverage_before.get("coverage_percent", 0))
        after_value = numeric(coverage_after.get("coverage_percent", 0))
        self.payload["sources_total"] = int(numeric(coverage_after.get("sources_total", coverage_before.get("sources_total", 0))))
        self.payload["coverage_before"] = before_value
        self.payload["coverage_after"] = after_value
        self.payload["coverage_change"] = round(after_value - before_value, 3)
        recommendation = coverage_after.get("additional_research_recommended", coverage_after.get("targeted_search_recommended", False))
        self.payload["targeted_search_recommended"] = boolean(recommendation)

    def save(self) -> None:
        """Atomically persist this manifest and retain only the newest bounded history."""
        try:
            history_dir = self.root / "output" / "research_runs"
            history_dir.mkdir(parents=True, exist_ok=True)
            timestamp = self.started_at.replace(":", "").replace("-", "").replace(".", "").replace("Z", "")
            filename = f"{timestamp}__{path_slug(self.args.brand)}__{path_slug(self.args.model)}.json"
            target = history_dir / filename
            atomic_write_json(target, self.payload)
            manifests = sorted(history_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
            for obsolete in manifests[:-MAX_RESEARCH_RUNS]:
                obsolete.unlink(missing_ok=True)
        except OSError as exc:
            print(f"history_warning=Nie udało się zapisać historii researchu: {safe_text(exc)}", file=sys.stderr)


def empty_fetch_summary() -> dict[str, str]:
    return {
        "fetch_status": "success",
        "offers_requested": "0",
        "offers_fetched": "0",
        "offers_failed": "0",
        "offers_skipped": "0",
    }


def parse_fetch_summary(output: str) -> dict[str, str]:
    summary = empty_fetch_summary()
    seen: set[str] = set()
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() in FETCH_KEYS:
            summary[key.strip()] = value.strip()
            seen.add(key.strip())
    if "fetch_status" not in seen:
        raise RuntimeError("Fetcher nie zwrócił fetch_status.")
    for key in FETCH_KEYS[1:]:
        if key not in seen:
            raise RuntimeError(f"Fetcher nie zwrócił licznika: {key}.")
        try:
            if int(summary[key]) < 0:
                raise ValueError
        except ValueError as exc:
            raise RuntimeError(f"Nieprawidłowy licznik fetchera: {key}={summary[key]}.") from exc
    if summary["fetch_status"] not in {"success", "partial", "failed"}:
        raise RuntimeError(f"Nieprawidłowy fetch_status: {summary['fetch_status']}.")
    return summary


def pipeline_status_for_fetch(fetch_status: str) -> str:
    if fetch_status == "partial":
        return "partial"
    if fetch_status == "success":
        return "success"
    return "failed"


def preview_summary(search_summary: object, new_offers: int) -> dict[str, str]:
    source = search_summary if isinstance(search_summary, dict) else {}
    result = {key: str(source.get(key, 0)) for key in PREVIEW_KEYS}
    # CSV is the authoritative list for the only value that can later be applied.
    result["new_offers"] = str(new_offers)
    return result


def print_preview_summary(group_key: str, summary: dict[str, str]) -> None:
    print("pipeline_status=preview")
    print("mode=preview")
    print(f"group_key={group_key}")
    for key in PREVIEW_KEYS:
        print(f"{key}={summary.get(key, '0')}")


def print_pipeline_summary(
    pipeline_status: str,
    group_key: str,
    new_offers: int,
    fetch: dict[str, str],
    coverage: dict[str, object],
    error: str = "",
    mode: str = "apply",
    offers_in_run: int = 0,
    offers_cleaned: int = 0,
    registry_records_updated: int = 0,
    groups_updated: int = 0,
) -> None:
    print(f"pipeline_status={pipeline_status}")
    print(f"mode={mode}")
    print(f"group_key={group_key}")
    print(f"new_offers={new_offers}")
    for key in FETCH_KEYS[1:]:
        print(f"{key}={fetch.get(key, '0')}")
    print(f"offers_in_run={offers_in_run}")
    print(f"offers_cleaned={offers_cleaned}")
    print(f"registry_records_updated={registry_records_updated}")
    print(f"groups_updated={groups_updated}")
    print(f"sources_total={coverage.get('sources_total', 0)}")
    print(f"coverage_percent={coverage.get('coverage_percent', 0)}")
    if error:
        print(f"error={error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Uruchamia pełny research jednego modelu.")
    parser.add_argument("--marketplace", required=True)
    parser.add_argument("--brand", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--category-key", help="Kanoniczna kategoria z rejestru FIELDNOTE.")
    parser.add_argument("--benchmark-group", help="Grupa benchmarkowa zgodna z kategorią.")
    parser.add_argument("--apply", action="store_true", help="Dodaje nowe aukcje do kolejki i pobiera ich karty.")
    parser.add_argument("--resume", action="store_true", help="Wznawia na zapisanych listingach i stanach modelu.")
    parser.add_argument("--skip-ai", action="store_true", help="Pomija kaskadową ekstrakcję AI.")
    parser.add_argument("--skip-product-profile", action="store_true", help="Pozostawia opcjonalny profil parent workerowi API.")
    parser.add_argument("--retry-errors", action="store_true", help="Ponawia błędne pobrania bez targeted search ani dodawania ofert do kolejki.")
    parser.add_argument("--fixture-scenario", choices=FIXTURE_SCENARIOS, help="Uruchamia izolowany scenariusz demonstracyjny bez API i bez modyfikacji produkcyjnych danych.")
    parser.add_argument("--fixture-root", help="Katalog fixture używany wyłącznie razem z --fixture-scenario.")
    parser.add_argument("--run-context", help="Immutable context utworzony przez lokalne API dla jednego uruchomienia.")
    parser.add_argument("--cancel-check-file", help="Tymczasowy sygnał anulowania workera; nie jest źródłem stanu runu.")
    return parser.parse_args()


def fixture_root_is_safe(value: str) -> bool:
    root = Path(value).expanduser().resolve()
    production_output = (ROOT / "output").resolve()
    try:
        root.relative_to(production_output)
        return False
    except ValueError:
        return True


def run_fixture_scenario(args: argparse.Namespace) -> int:
    """Emit deterministic pipeline output without calling the network or production scripts."""
    if not args.fixture_root:
        print("pipeline_status=failed")
        print("mode=apply")
        print("error=--fixture-root jest wymagany w trybie fixture.")
        return 1
    if not fixture_root_is_safe(args.fixture_root):
        print("pipeline_status=failed")
        print("mode=apply")
        print("error=--fixture-root nie może znajdować się w produkcyjnym output/.")
        return 1
    fixture_root = Path(args.fixture_root).expanduser().resolve()
    if not fixture_root.exists():
        print("pipeline_status=failed")
        print("mode=apply")
        print("error=Nie znaleziono katalogu fixture.")
        return 1

    group_key = f"{normalized(args.brand)}|{normalized(args.model)}"
    scenario = args.fixture_scenario
    mode = "preview" if scenario == "empty_results" else "apply"
    history = ResearchRun(fixture_root, args, group_key, mode)
    print(f"fixture_root={fixture_root}")
    print(f"fixture_scenario={scenario}")
    try:
        if scenario == "empty_results":
            run_stage(1, "targeted search", None, "fixture: no matching offers", history=history)
            preview = {
                "cards_found": "0", "unique_offer_ids": "0", "accepted_model_offers": "0",
                "rejected_other_models": "0", "already_known": "0", "new_offers": "0",
            }
            history.update_summary(preview=preview, new_offers=0)
            history.complete("preview")
            print_preview_summary(group_key, preview)
            return 0

        labels = (
            "targeted search", "merge", "fetch offer pages", "technical cleaner", "source registry",
            "model groups", "model facts cascade", "model benchmark", "coverage report",
        )
        stage_count = 3 if scenario == "failed" else len(labels)
        for index, label in enumerate(labels[:stage_count], start=1):
            detail = "fixture: skipped; no AI" if label == "model facts cascade" else f"fixture: {scenario}"
            status = "failed" if scenario == "failed" and index == 3 else "partial" if scenario == "partial" and index == 3 else "success"
            record = history.start_stage(index, label)
            print(f"[{index}/9] {label} ({detail})")
            history.finish_stage(record, status, detail)

        if scenario == "success":
            fetch = {"fetch_status": "success", "offers_requested": "2", "offers_fetched": "2", "offers_failed": "0", "offers_skipped": "0"}
            coverage = {"sources_total": 2, "coverage_percent": 66.67, "targeted_search_recommended": False}
            history.update_summary(
                fetch=fetch, coverage_after=coverage, new_offers=2,
                offers_in_run=2, offers_cleaned=2, registry_records_updated=2, groups_updated=1,
            )
            history.complete("success")
            print_pipeline_summary(
                "success", group_key, 2, fetch, coverage,
                offers_in_run=2, offers_cleaned=2, registry_records_updated=2, groups_updated=1,
            )
            return 0
        if scenario == "partial":
            fetch = {"fetch_status": "partial", "offers_requested": "2", "offers_fetched": "1", "offers_failed": "1", "offers_skipped": "0"}
            coverage = {"sources_total": 2, "coverage_percent": 50.0, "targeted_search_recommended": True}
            history.update_summary(
                fetch=fetch, coverage_after=coverage, new_offers=2,
                offers_in_run=2, offers_cleaned=1, registry_records_updated=1, groups_updated=1,
            )
            history.complete("partial")
            print_pipeline_summary(
                "partial", group_key, 2, fetch, coverage,
                offers_in_run=2, offers_cleaned=1, registry_records_updated=1, groups_updated=1,
            )
            return 0

        fetch = {"fetch_status": "failed", "offers_requested": "1", "offers_fetched": "0", "offers_failed": "1", "offers_skipped": "0"}
        message = "Fixture symuluje błąd pobrania Firecrawl."
        history.update_summary(fetch=fetch, new_offers=1, offers_in_run=1)
        history.complete("failed", error_stage="fetch offer pages", error_message=message)
        print_pipeline_summary("failed", group_key, 1, fetch, {}, message, offers_in_run=1)
        return 1
    finally:
        if not history.payload.get("finished_at"):
            history.complete("failed", error_stage="fixture", error_message="Fixture nie zakończył się poprawnie.")
        history.save()


def main() -> int:
    args = parse_args()
    run_stage.cancel_check_file = args.cancel_check_file
    immutable_context = load_run_context(args.run_context)
    if args.fixture_scenario:
        return run_fixture_scenario(args)
    marketplace = normalized(args.marketplace)
    mode = "retry" if args.retry_errors else "apply" if args.apply else "preview"
    group_key = f"{normalized(args.brand)}|{normalized(args.model)}"
    if immutable_context:
        context_group_key = str(immutable_context.get("group_key", ""))
        if context_group_key != group_key:
            print("pipeline_status=failed")
            print(f"mode={mode}")
            print("error=Run context nie pasuje do wskazanego produktu.")
            return 1
    history = ResearchRun(ROOT, args, group_key, mode)
    if immutable_context:
        history.run_id = str(immutable_context["run_id"])
        history.payload["run_id"] = history.run_id
        history.payload["run_context_path"] = str(args.run_context)
        history.payload["pipeline_version"] = str(immutable_context.get("pipeline_version", ""))
    coverage_before = coverage_for_group(group_key)
    fetch_summary = empty_fetch_summary()
    new_rows: list[dict[str, str]] = []
    search_summary: dict[str, str] = {}
    coverage: dict[str, object] = {}
    new_offer_ids: set[str] = set()
    reused_offer_ids: set[str] = set()
    retry_offer_ids: set[str] = set()
    fetched_offer_ids: set[str] = set()
    failed_offer_ids: set[str] = set()
    offers_in_run = 0
    offers_cleaned = 0
    registry_records_updated = 0
    groups_updated = 0
    analysis_partial = False
    analysis_error_message = ""
    context_path: Path | None = None
    current_stage = "validation"

    existing_catalog_product = product_for_group_key(group_key)
    requested_category_key = str(args.category_key or existing_catalog_product.get("category_key", "")).strip()
    requested_benchmark_group = str(args.benchmark_group or existing_catalog_product.get("benchmark_group", "")).strip()
    try:
        category_assignment = validate_category_assignment(
            requested_category_key,
            requested_benchmark_group,
            require_complete=bool(args.apply),
        )
    except CategoryValidationError as exc:
        print(f"pipeline_status=failed\nmode={mode}\nerror={exc.code}: {exc.message}")
        history.complete("failed", error_stage=current_stage, error_message=f"{exc.code}: {exc.message}")
        history.save()
        return 2

    if marketplace != "allegro":
        print("pipeline_status=failed")
        print(f"mode={mode}")
        print(f"error=Marketplace '{args.marketplace}' nie ma jeszcze adaptera.")
        history.complete("failed", error_stage=current_stage, error_message=f"Marketplace '{args.marketplace}' nie ma jeszcze adaptera.")
        history.save()
        return 1
    if args.retry_errors and not args.apply:
        print("pipeline_status=failed")
        print("mode=preview")
        print("error=--retry-errors wymaga --apply, ponieważ zmienia statusy kolejki.")
        history.complete("failed", error_stage=current_stage, error_message="--retry-errors wymaga --apply, ponieważ zmienia statusy kolejki.")
        history.save()
        return 1

    # An apply run owns an explicit product identity before any source is
    # fetched. Preview remains read-only by design.
    if args.apply:
        try:
            catalog_product = ensure_catalog_product(
                args.brand,
                args.model,
                category_key=category_assignment["category_key"],
                benchmark_group=category_assignment["benchmark_group"],
            )
            group_directory = ensure_group_directory(catalog_product)
            print(f"catalog_product_id={catalog_product['product_id']}")
            print(f"catalog_group_directory={group_directory.relative_to(ROOT)}")
        except ValueError as exc:
            print(f"pipeline_status=failed\nmode={mode}\nerror={exc}")
            history.complete("failed", error_stage=current_stage, error_message=str(exc))
            history.save()
            return 1

    targeted_dir = ROOT / "input" / "targeted_search" / f"{path_slug(args.brand)}__{path_slug(args.model)}" / marketplace
    summary_path = targeted_dir / "research_summary.json"
    shared_new_offers_path = targeted_dir / "new_offers.csv"
    candidate_offers_path = targeted_dir / "candidate_offers.csv"
    new_offers_path = shared_new_offers_path

    try:
        if args.retry_errors:
            # Retry mode never searches or merges: it touches only existing error rows.
            current_stage = "targeted search"
            run_stage(1, "targeted search", None, "skipped: retry errors", history=history)
            current_stage = "merge"
            run_stage(2, "merge", None, "skipped: retry errors", history=history)
            retry_offer_ids = retry_offer_ids_for_model(marketplace, args.brand, args.model)
            offers_in_run = len(retry_offer_ids)
            if retry_offer_ids:
                fetch_command = [
                    sys.executable,
                    str(SCRIPTS / "fetch_firecrawl_offer_pages.py"),
                    "--retry-errors",
                    "--limit",
                    str(len(retry_offer_ids)),
                ]
                for offer_id in sorted(retry_offer_ids):
                    fetch_command.extend(["--offer-id", offer_id])
                current_stage = "fetch offer pages"
                fetch_output, fetch_returncode = run_stage(3, "fetch offer pages", fetch_command, "retry errors", allow_failure=True, history=history)
                fetch_summary = parse_fetch_summary(fetch_output)
                fetched_offer_ids = offer_ids_with_status(retry_offer_ids, "fetched")
                failed_offer_ids = offer_ids_with_status(retry_offer_ids, "error")
                history.update_latest_stage(
                    fetch_summary["fetch_status"],
                    f"fetched={fetch_summary['offers_fetched']}, failed={fetch_summary['offers_failed']}, skipped={fetch_summary['offers_skipped']}",
                )
                if fetch_returncode and fetch_summary["fetch_status"] != "failed":
                    raise RuntimeError("Fetcher zakończył się błędem bez statusu failed.")
                if fetch_summary["fetch_status"] == "failed":
                    raise RuntimeError(
                        "Ponowienie pobierania kart ofert nie powiodło się: "
                        f"{fetch_summary['offers_failed']} błędów, "
                        f"{fetch_summary['offers_skipped']} pominiętych."
                    )
            else:
                current_stage = "fetch offer pages"
                run_stage(3, "fetch offer pages", None, "no retryable errors for this model", history=history)
        else:
            # Preserve the original Firecrawl listing response when resuming an existing run.
            if args.resume and summary_path.exists() and shared_new_offers_path.exists() and (targeted_dir / "listing.html").exists():
                current_stage = "targeted search"
                run_stage(1, "targeted search", None, "resume: existing listing", history=history)
            else:
                command = [sys.executable, str(SCRIPTS / "fetch_targeted_model_offers.py"), "--marketplace", marketplace, "--brand", args.brand, "--model", args.model, "--category-key", category_assignment["category_key"]]
                current_stage = "targeted search"
                run_stage(1, "targeted search", command, history=history)

            if immutable_context:
                destination = ROOT / str(immutable_context.get("selected_offers_csv", ""))
                selected_ids = {str(value) for value in immutable_context.get("selected_offer_ids", []) if str(value)}
                # The immutable UI selection is authoritative. Unlike
                # candidate_offers.csv, the full listing retains known offers
                # that may be reusable or may require one explicit fetch.
                selection_source = targeted_dir / "extracted_offers.json"
                if selection_source.exists():
                    # Convert the listing JSON to the CSV shape expected by the
                    # materializer without changing shared search artifacts.
                    listing_rows = read_json(selection_source, [])
                    staging_source = destination.with_name("selected_listing.csv")
                    if isinstance(listing_rows, list):
                        listing_fields = sorted({key for row in listing_rows if isinstance(row, dict) for key in row})
                        atomic_write_csv(staging_source, listing_fields, [row for row in listing_rows if isinstance(row, dict)], preserve_previous=False)
                        selection_source = staging_source
                else:
                    selection_source = candidate_offers_path if candidate_offers_path.exists() else shared_new_offers_path
                new_rows = materialize_selected_offers(selection_source, destination, selected_ids)
                new_offers_path = destination
            else:
                new_rows = read_csv(shared_new_offers_path)
            if not args.apply:
                search_summary = preview_summary(read_json(summary_path, {}), len(new_rows))
                history.update_summary(preview=search_summary, coverage_before=coverage_before, coverage_after=coverage_before, new_offers=len(new_rows))
                history.complete("preview")
                print_preview_summary(group_key, search_summary)
                return 0

            reused_offer_ids = {
                row.get("external_offer_id", "")
                for row in new_rows
                if row.get("external_offer_id", "") and row.get("owned_run_status") == "reused"
            }
            fetch_rows = [row for row in new_rows if row.get("owned_run_status") == "fetch"]
            new_offer_ids = {row.get("external_offer_id", "") for row in fetch_rows if row.get("external_offer_id", "")}
            offers_in_run = len(new_rows)
            for row in new_rows:
                print(f"selected_offer={row.get('external_offer_id', '')} result={row.get('owned_run_status', 'fetch')}")

            existing_queue_ids = prepare_selected_offer_queue(new_offer_ids)
            new_queue_rows = [row for row in fetch_rows if row.get("external_offer_id", "") not in existing_queue_ids]
            if new_queue_rows:
                new_queue_path = new_offers_path.with_name("selected_new_queue_offers.csv")
                atomic_write_csv(new_queue_path, list(new_queue_rows[0]), new_queue_rows, preserve_previous=False)
                merge_command = [sys.executable, str(SCRIPTS / "merge_targeted_model_offers.py"), "--marketplace", marketplace, "--brand", args.brand, "--model", args.model, "--input-csv", str(new_queue_path)]
                current_stage = "merge"
                run_stage(2, "merge", merge_command, history=history)
                add_new_offers_to_queue(new_queue_rows, args.brand, args.model)
            elif fetch_rows:
                current_stage = "merge"
                run_stage(2, "merge", None, "selected existing offers queued for one fetch", history=history)
            else:
                current_stage = "merge"
                run_stage(2, "merge", None, "selected snapshots reused", history=history)

            if new_offer_ids:
                move_queue_rows_first(new_offer_ids)
                fetch_command = [
                    sys.executable,
                    str(SCRIPTS / "fetch_firecrawl_offer_pages.py"),
                    "--limit",
                    str(len(new_offer_ids)),
                ]
                if any((ROOT / "input" / "firecrawl_offer_pages" / offer_id).exists() for offer_id in new_offer_ids):
                    fetch_command.append("--force")
                for offer_id in sorted(new_offer_ids):
                    fetch_command.extend(["--offer-id", offer_id])
                current_stage = "fetch offer pages"
                fetch_output, fetch_returncode = run_stage(3, "fetch offer pages", fetch_command, allow_failure=True, history=history)
                fetch_summary = parse_fetch_summary(fetch_output)
                fetched_offer_ids = offer_ids_with_status(new_offer_ids, "fetched")
                failed_offer_ids = offer_ids_with_status(new_offer_ids, "error")
                history.update_latest_stage(
                    fetch_summary["fetch_status"],
                    f"fetched={fetch_summary['offers_fetched']}, failed={fetch_summary['offers_failed']}, skipped={fetch_summary['offers_skipped']}",
                )
                if fetch_returncode and fetch_summary["fetch_status"] != "failed":
                    raise RuntimeError("Fetcher zakończył się błędem bez statusu failed.")
                if fetch_summary["fetch_status"] == "failed":
                    raise RuntimeError(
                        "Pobieranie kart ofert nie powiodło się: "
                        f"{fetch_summary['offers_failed']} błędów, "
                        f"{fetch_summary['offers_skipped']} pominiętych."
                    )
            else:
                current_stage = "fetch offer pages"
                run_stage(3, "fetch offer pages", None, "no new pending offers", history=history)

        run_context = {
            "run_id": history.run_id,
            "marketplace": marketplace,
            "brand": args.brand,
            "model": args.model,
            "group_key": group_key,
            "new_offer_ids": sorted(new_offer_ids),
            "reused_offer_ids": sorted(reused_offer_ids),
            "fetched_offer_ids": sorted(fetched_offer_ids),
            "failed_offer_ids": sorted(failed_offer_ids),
            "retry_offer_ids": sorted(retry_offer_ids),
            "selected_manufacturer_source_ids": [
                str(value) for value in immutable_context.get("selected_manufacturer_source_ids", [])
                if str(value).strip()
            ] if immutable_context else [],
            "include_manufacturer_sources": bool(immutable_context.get("include_manufacturer_sources")) if immutable_context else False,
        }
        context_path = write_run_context(run_context)

        if fetched_offer_ids:
            current_stage = "technical cleaner"
            cleaner_output, _ = run_stage(
                4,
                "technical cleaner",
                [sys.executable, str(SCRIPTS / "clean_offer_pages_technical.py"), "--offer-ids-file", str(context_path)],
                f"{len(fetched_offer_ids)} fetched offers from this run",
                history=history,
            )
            offers_cleaned = output_counter(cleaner_output, "offers_cleaned")

            current_stage = "source registry"
            registry_output, _ = run_stage(
                5,
                "source registry",
                [sys.executable, str(SCRIPTS / "build_source_registry.py"), "--offer-ids-file", str(context_path)],
                f"{len(fetched_offer_ids)} fetched offers from this run",
                history=history,
            )
            registry_records_updated = output_counter(registry_output, "registry_records_updated")

            current_stage = "model groups"
            groups_output, _ = run_stage(
                6,
                "model groups",
                [
                    sys.executable, str(SCRIPTS / "build_model_groups.py"), "--max-offers-per-model", "5",
                    "--force", "--group-key", group_key,
                ],
                f"only {group_key}",
                history=history,
            )
            groups_updated = output_counter(groups_output, "groups_updated")
        else:
            current_stage = "technical cleaner"
            run_stage(4, "technical cleaner", None, "no fetched offers in this run", history=history)
            current_stage = "source registry"
            run_stage(5, "source registry", None, "no fetched offers in this run", history=history)
            current_stage = "model groups"
            run_stage(6, "model groups", None, "no fetched offers in this run", history=history)

        current_stage = "model facts cascade"
        if args.retry_errors:
            run_stage(7, "model facts cascade", None, "skipped after retry errors", history=history)
        elif args.skip_ai:
            run_stage(7, "model facts cascade", None, "skipped by --skip-ai", history=history)
        elif args.resume and not group_has_unprocessed_sources(group_key):
            run_stage(7, "model facts cascade", None, "resume: no unprocessed sources", history=history)
        else:
            cascade_command = [sys.executable, str(SCRIPTS / "extract_model_facts_cascade.py"), "--group-key", group_key]
            if args.resume:
                cascade_command.append("--resume")
            cascade_output, cascade_code = run_stage(
                7,
                "model facts cascade",
                cascade_command,
                allow_failure=True,
                history=history,
            )
            if is_controlled_source_analysis_failure(cascade_code, cascade_output):
                analysis_partial = True
                analysis_error_message = controlled_source_analysis_message(cascade_output)
                history.update_latest_stage("partial", analysis_error_message)
                print("analysis_status=partial")
                print(f"analysis_error_message={analysis_error_message}")
            elif cascade_code:
                raise RuntimeError("Etap 7/9 nie powiódł się: model facts cascade")

        current_stage = "model benchmark"
        run_stage(8, "model benchmark", [sys.executable, str(SCRIPTS / "build_model_benchmark.py")], history=history)
        current_stage = "coverage report"
        run_stage(9, "coverage report", [sys.executable, str(SCRIPTS / "report_model_coverage.py")], history=history)

        # Optional narrative profile never blocks the factual research result.
        current_stage = "product profile generation"
        if args.skip_product_profile:
            run_stage(10, "product profile generation", None, "skipped_by_parent_api_worker", history=history)
        elif os.getenv("PRODUCT_PROFILE_AI_ENABLED", "").lower() in {"1", "true", "yes"}:
            profile_output, profile_code = run_stage(
                10,
                "product profile generation",
                [sys.executable, str(SCRIPTS / "generate_product_profile.py"), "--product-slug", f"{path_slug(args.brand)}__{path_slug(args.model)}", "--allow-openai", "--owned-lock-run-id", history.run_id],
                "optional source-backed narrative profile",
                allow_failure=True,
                history=history,
            )
            history.update_latest_stage("completed" if profile_code == 0 else "partial", profile_output[-500:])
        else:
            run_stage(10, "product profile generation", None, "disabled_by_PRODUCT_PROFILE_AI_ENABLED", history=history)

        coverage = coverage_for_group(group_key)
        if not coverage:
            raise RuntimeError(f"Brak rekordu coverage dla {group_key}")
        pipeline_status = pipeline_status_for_fetch(fetch_summary["fetch_status"])
        if analysis_partial and pipeline_status == "success":
            pipeline_status = "partial"
        history.update_summary(
            preview=search_summary, fetch=fetch_summary, coverage_before=coverage_before, coverage_after=coverage,
            new_offers=len(new_rows), offers_in_run=offers_in_run, offers_cleaned=offers_cleaned,
            registry_records_updated=registry_records_updated, groups_updated=groups_updated,
        )
        history.complete(pipeline_status)
        print_pipeline_summary(
            pipeline_status, group_key, len(new_rows), fetch_summary, coverage, mode=mode,
            offers_in_run=offers_in_run, offers_cleaned=offers_cleaned,
            registry_records_updated=registry_records_updated, groups_updated=groups_updated,
        )
        return 0
    except RunCancelledError as exc:
        history.update_latest_stage("cancelled", exc)
        history.complete("cancelled", error_stage=current_stage, error_message=exc)
        print("pipeline_status=cancelled")
        return 0
    except (RuntimeError, OSError, ValueError) as exc:
        coverage = coverage or coverage_for_group(group_key)
        history.update_latest_stage("failed", exc)
        history.update_summary(
            preview=search_summary, fetch=fetch_summary, coverage_before=coverage_before, coverage_after=coverage,
            new_offers=len(new_rows), offers_in_run=offers_in_run, offers_cleaned=offers_cleaned,
            registry_records_updated=registry_records_updated, groups_updated=groups_updated,
        )
        history.complete("failed", error_stage=current_stage, error_message=exc)
        if args.apply:
            print_pipeline_summary(
                "failed", group_key, len(new_rows), fetch_summary, coverage, str(exc), mode=mode,
                offers_in_run=offers_in_run, offers_cleaned=offers_cleaned,
                registry_records_updated=registry_records_updated, groups_updated=groups_updated,
            )
        else:
            print("pipeline_status=failed")
            print("mode=preview")
            print(f"group_key={group_key}")
            print(f"error={exc}")
        return 1
    finally:
        if context_path:
            context_path.unlink(missing_ok=True)
        if not history.payload.get("finished_at"):
            history.complete("failed", error_stage=current_stage, error_message="Pipeline zakończył się bez wyniku końcowego.")
        history.save()


if __name__ == "__main__":
    raise SystemExit(main())
