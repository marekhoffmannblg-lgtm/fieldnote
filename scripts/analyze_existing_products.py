#!/usr/bin/env python3
"""One-off sequential migration of products from saved FIELDNOTE snapshots.

The script deliberately does not search Allegro or fetch Firecrawl pages when
used with ``--no-fetch``. It only rebuilds derived artifacts and invokes the
existing AI cascade on snapshots already stored locally.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
GROUPS = ROOT / "output" / "model_groups"
SCRIPTS = ROOT / "scripts"
STATUS_PATH = ROOT / "output" / "product_analysis_status.json"
MIGRATIONS = ROOT / "output" / "existing_product_migrations"
AUDIT_PATH = ROOT / "output" / "migrations" / "existing_products_audit.json"
API_RUNS = ROOT / "fieldnote-api" / "runs"
BENCHMARK_PATH = ROOT / "output" / "model_benchmark.csv"
COVERAGE_PATH = ROOT / "output" / "model_coverage.csv"
REGISTRY_PATH = ROOT / "output" / "source_registry.jsonl"
FRONTEND_PRODUCTS = ROOT / "fieldnote-frontend" / "src" / "data" / "generated" / "products"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_dotenv() -> None:
    """Load local API credentials without echoing their values."""
    env_path = ROOT / "fieldnote-api" / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"OPENAI_API_KEY", "FIRECRAWL_API_KEY"} and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def local_snapshot_exists(source: dict[str, Any]) -> bool:
    candidates: list[Path] = []
    for name in ("content_path", "offer_sections_path"):
        value = str(source.get(name, "") or "").strip()
        if value:
            path = ROOT / value
            candidates.extend([path, path.parent / "markdown.md", path.parent / "technical_clean.md"])
    for name in ("manufacturer_source_path",):
        value = str(source.get(name, "") or "").strip()
        if value:
            path = ROOT / value
            candidates.extend([path / "markdown.md", path / "technical_clean.md"])
    return any(path.is_file() for path in candidates)


def group_candidates(product_slug: str | None) -> list[tuple[Path, dict[str, Any]]]:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for group_path in sorted(GROUPS.glob("*/group.json")):
        if product_slug and group_path.parent.name != product_slug:
            continue
        group = read_json(group_path, {})
        sources = [item for item in group.get("sources", []) if isinstance(item, dict)] if isinstance(group, dict) else []
        if group.get("group_key") and any(local_snapshot_exists(source) for source in sources):
            candidates.append((group_path.parent, group))
    return candidates


def load_csv_groups(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        return {str(row.get("group_key", "")).strip() for row in csv.DictReader(handle) if row.get("group_key")}


def registry_source_ids() -> set[str]:
    if not REGISTRY_PATH.exists():
        return set()
    result: set[str] = set()
    for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("source_id"):
            result.add(str(value["source_id"]))
    return result


def source_snapshot_counts(group: dict[str, Any]) -> tuple[int, int]:
    raw_directories: set[Path] = set()
    clean_directories: set[Path] = set()
    for source in group.get("sources", []):
        if not isinstance(source, dict):
            continue
        candidates: list[Path] = []
        for name in ("content_path", "offer_sections_path"):
            value = str(source.get(name, "") or "").strip()
            if value:
                candidates.append((ROOT / value).parent)
        value = str(source.get("manufacturer_source_path", "") or "").strip()
        if value:
            candidates.append(ROOT / value)
        for directory in candidates:
            if (directory / "markdown.md").is_file() or (directory / "page.html").is_file():
                raw_directories.add(directory)
            if (directory / "technical_clean.md").is_file():
                clean_directories.add(directory)
    return len(raw_directories), len(clean_directories)


def load_runs_by_product() -> dict[str, list[dict[str, Any]]]:
    runs: dict[str, list[dict[str, Any]]] = {}
    for path in API_RUNS.glob("*.json"):
        value = read_json(path, {})
        slug = str(value.get("product_slug", "") or "").strip()
        if slug:
            value["_path"] = str(path.relative_to(ROOT))
            runs.setdefault(slug, []).append(value)
    for values in runs.values():
        values.sort(key=lambda item: str(item.get("started_at") or item.get("updated_at") or ""))
    return runs


def latest_migration(slug: str) -> dict[str, Any]:
    value = read_json(MIGRATIONS / f"{slug}.json", {})
    return value if isinstance(value, dict) else {}


def audit_products(candidates: list[tuple[Path, dict[str, Any]],], statuses: dict[str, Any]) -> list[dict[str, Any]]:
    benchmark_groups = load_csv_groups(BENCHMARK_PATH)
    coverage_groups = load_csv_groups(COVERAGE_PATH)
    registry_ids = registry_source_ids()
    runs_by_product = load_runs_by_product()
    result: list[dict[str, Any]] = []
    for directory, group in candidates:
        slug = directory.name
        group_key = str(group.get("group_key", ""))
        state = read_json(directory / "model_state.json", {})
        fields = state.get("fields", {}) if isinstance(state, dict) else {}
        source_ids = {str(source.get("source_id", "")) for source in group.get("sources", []) if isinstance(source, dict) and source.get("source_id")}
        raw_count, clean_count = source_snapshot_counts(group)
        product_path = FRONTEND_PRODUCTS / f"{slug}.json"
        final_product_exists = bool(fields) and group_key in benchmark_groups and product_path.exists()
        benchmark_exists = group_key in benchmark_groups
        coverage_exists = group_key in coverage_groups
        valid_final_result = final_product_exists and coverage_exists
        product_runs = runs_by_product.get(slug, [])
        successful_runs = [run for run in product_runs if run.get("status") == "success"]
        latest_run = product_runs[-1] if product_runs else {}
        migration = latest_migration(slug)
        latest_run_status = str(latest_run.get("status", "") or migration.get("status", "") or "none")
        latest_failed_step = ""
        if latest_run_status == "failed":
            latest_failed_step = str(latest_run.get("current_step", "") or latest_run.get("error", ""))
        if not latest_failed_step and migration.get("status") == "analysis_failed":
            latest_failed_step = str(migration.get("error", ""))
        current = statuses.get(slug, {}) if isinstance(statuses, dict) else {}
        if valid_final_result:
            final_status = "ready"
            reason = "valid_final_result"
            action = "keep_ready"
        elif raw_count == 0:
            final_status = "refresh_recommended"
            reason = "no_usable_local_sources"
            action = "full_research_required"
        elif latest_run_status == "failed" or migration.get("status") == "analysis_failed":
            final_status = "analysis_failed"
            reason = "technical_pipeline_error_without_final_result"
            action = "resume_local_analysis"
        else:
            final_status = "refresh_recommended"
            reason = "local_analysis_not_completed"
            action = "resume_local_analysis"
        result.append({
            "product_slug": slug,
            "group_key": group_key,
            "sources_count": len(source_ids),
            "raw_snapshots_count": raw_count,
            "clean_snapshots_count": clean_count,
            "successful_runs_count": len(successful_runs),
            "latest_run_status": latest_run_status,
            "latest_failed_step": latest_failed_step,
            "final_product_exists": final_product_exists,
            "benchmark_exists": benchmark_exists,
            "coverage_exists": coverage_exists,
            "source_registry_exists": bool(source_ids) and source_ids.issubset(registry_ids),
            "current_status": str(current.get("status", "")),
            "valid_final_result": valid_final_result,
            "final_status": final_status,
            "reason": reason,
            "failure_reason": latest_failed_step if final_status == "analysis_failed" else "",
            "recommended_action": action,
        })
    return result


def write_audit(records: list[dict[str, Any]]) -> None:
    atomic_write(AUDIT_PATH, {"generated_at": now(), "products": records})


def repair_statuses(records: list[dict[str, Any]], statuses: dict[str, Any]) -> int:
    repaired = 0
    for record in records:
        slug = record["product_slug"]
        previous = statuses.get(slug, {}) if isinstance(statuses, dict) else {}
        if previous.get("status") != record["final_status"]:
            repaired += 1
        statuses[slug] = {
            "status": record["final_status"],
            "updated_at": now(),
            "group_key": record["group_key"],
            "reason": record["reason"],
            "error": record["latest_failed_step"] if record["final_status"] == "analysis_failed" else "",
        }
    save_status(statuses)
    return repaired


def save_status(statuses: dict[str, dict[str, Any]]) -> None:
    atomic_write(STATUS_PATH, statuses)


def cancel_stale_runs() -> int:
    cancelled = 0
    for path in API_RUNS.glob("*.json"):
        payload = read_json(path, {})
        if payload.get("status") not in {"queued", "running"}:
            continue
        # An old persisted 4% run cannot survive an API restart; mark it as a
        # failed/cancelled historical run instead of showing it as active.
        if int(payload.get("progress", 0) or 0) <= 4:
            payload.update({
                "status": "failed",
                "current_step": "Anulowano zawieszone uruchomienie podczas migracji",
                "error": "Uruchomienie nie kontynuowało pracy po restarcie lokalnej usługi.",
                "finished_at": now(),
                "updated_at": now(),
            })
            atomic_write(path, payload)
            cancelled += 1
    return cancelled


def run(command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output[-16000:]


def offer_ids(group: dict[str, Any]) -> list[str]:
    return [
        str(item.get("external_offer_id") or item.get("offer_id") or "").strip()
        for item in group.get("sources", []) if isinstance(item, dict)
        and str(item.get("external_offer_id") or item.get("offer_id") or "").strip()
    ]


def uncleaned_offer_ids(group: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for source in group.get("sources", []):
        if not isinstance(source, dict):
            continue
        value = str(source.get("offer_sections_path") or source.get("content_path") or "").strip()
        if not value:
            continue
        directory = (ROOT / value).parent
        raw = directory / "markdown.md"
        clean = directory / "technical_clean.md"
        identifier = str(source.get("external_offer_id") or source.get("offer_id") or "").strip()
        if identifier and raw.exists() and not clean.exists():
            result.append(identifier)
    return sorted(set(result))


def process_product(directory: Path, group: dict[str, Any], args: argparse.Namespace, statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    slug = directory.name
    group_key = str(group["group_key"])
    started = now()
    item: dict[str, Any] = {"product_slug": slug, "group_key": group_key, "started_at": started, "status": "analysis_running", "steps": [], "error": ""}
    ids = offer_ids(group)
    context_path: Path | None = None
    if args.dry_run:
        item["steps"].append({"name": "plan", "status": "planned", "sources": len(ids), "uncleaned": len(uncleaned_offer_ids(group))})
        item["status"] = "planned"
        item["finished_at"] = now()
        return item
    statuses[slug] = {"status": "analysis_running", "updated_at": started, "group_key": group_key}
    save_status(statuses)
    try:
        if not args.no_fetch:
            raise RuntimeError("Ten skrypt migracyjny obsługuje wyłącznie lokalne snapshoty. Użyj --no-fetch.")
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Brak OPENAI_API_KEY. Migracja nie może uruchomić ekstrakcji AI.")

        dirty = uncleaned_offer_ids(group)
        if dirty:
            command = [sys.executable, str(SCRIPTS / "clean_offer_pages_technical.py")]
            for identifier in dirty:
                command.extend(["--offer-id", identifier])
            ok, output = run(command)
            item["steps"].append({"name": "technical_cleaner", "status": "success" if ok else "failed", "output": output})
            if not ok:
                raise RuntimeError("technical_cleaner")
        else:
            item["steps"].append({"name": "technical_cleaner", "status": "skipped", "output": "all local snapshots already clean"})

        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump({"fetched_offer_ids": ids}, handle)
            context_path = Path(handle.name)
        for name, command in (
            ("source_registry", [sys.executable, str(SCRIPTS / "build_source_registry.py"), "--offer-ids-file", str(context_path)]),
            ("model_grouping", [sys.executable, str(SCRIPTS / "build_model_groups.py"), "--group-key", group_key, "--max-offers-per-model", "5", "--force"]),
        ):
            ok, output = run(command)
            item["steps"].append({"name": name, "status": "success" if ok else "failed", "output": output})
            if not ok:
                raise RuntimeError(name)

        state = read_json(directory / "model_state.json", {})
        processed = {str(value) for value in state.get("processed_source_ids", []) if str(value)} if isinstance(state, dict) else set()
        source_ids = {str(source.get("source_id", "")) for source in group.get("sources", []) if isinstance(source, dict) and str(source.get("source_id", ""))}
        if args.resume and source_ids and source_ids.issubset(processed):
            item["steps"].append({"name": "ai_extraction", "status": "skipped", "output": "all saved sources were already analysed"})
        else:
            cascade = [sys.executable, str(SCRIPTS / "extract_model_facts_cascade.py"), "--group-key", group_key]
            if args.resume:
                cascade.append("--resume")
            ok, output = run(cascade)
            item["steps"].append({"name": "ai_extraction", "status": "success" if ok else "failed", "output": output})
            if not ok:
                raise RuntimeError("ai_extraction")

        for name, command in (
            ("benchmark", [sys.executable, str(SCRIPTS / "build_model_benchmark.py")]),
            ("coverage", [sys.executable, str(SCRIPTS / "report_model_coverage.py")]),
        ):
            ok, output = run(command)
            item["steps"].append({"name": name, "status": "success" if ok else "failed", "output": output})
            if not ok:
                raise RuntimeError(name)
        item["status"] = "ready"
        statuses[slug] = {"status": "ready", "updated_at": now(), "group_key": group_key}
    except RuntimeError as exc:
        item["status"] = "analysis_failed"
        item["error"] = str(exc)
        statuses[slug] = {"status": "analysis_failed", "updated_at": now(), "group_key": group_key, "error": str(exc)}
    finally:
        if context_path:
            context_path.unlink(missing_ok=True)
        item["finished_at"] = now()
        save_status(statuses)
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description="Analizuje produkty wyłącznie z zapisanych snapshotów.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true")
    scope.add_argument("--product-slug")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--repair-statuses", action="store_true", help="Napraw statusy na podstawie istniejących, poprawnych artefaktów.")
    parser.add_argument("--repair-only", action="store_true", help="Zapisz wyłącznie naprawione statusy i raport; nie uruchamiaj ekstrakcji AI.")
    args = parser.parse_args()
    load_dotenv()
    candidates = group_candidates(args.product_slug)
    if args.product_slug and not candidates:
        print(f"Nie znaleziono produktu z lokalnymi snapshotami: {args.product_slug}")
        return 1
    statuses = read_json(STATUS_PATH, {})
    statuses = statuses if isinstance(statuses, dict) else {}
    audit_before = audit_products(candidates, statuses)
    write_audit(audit_before)
    repaired_before = 0
    if args.repair_statuses and not args.dry_run:
        repaired_before = repair_statuses(audit_before, statuses)
    cancelled = 0 if args.dry_run or args.repair_only else cancel_stale_runs()
    MIGRATIONS.mkdir(parents=True, exist_ok=True)
    migration = {
        "started_at": now(), "no_fetch": args.no_fetch, "dry_run": args.dry_run,
        "repair_statuses": args.repair_statuses, "status_repairs_before": repaired_before,
        "cancelled_stale_runs": cancelled, "products": [],
    }
    audit_by_slug = {item["product_slug"]: item for item in audit_before}
    for directory, group in candidates:
        audit = audit_by_slug[directory.name]
        if args.repair_only:
            result = {
                "product_slug": directory.name,
                "group_key": audit["group_key"],
                "started_at": now(), "finished_at": now(), "status": audit["final_status"],
                "steps": [{"name": "status_repair", "status": "success", "output": audit["reason"]}],
                "error": audit["latest_failed_step"] if audit["final_status"] == "analysis_failed" else "",
            }
        elif audit["valid_final_result"]:
            result = {
                "product_slug": directory.name,
                "group_key": audit["group_key"],
                "started_at": now(), "finished_at": now(), "status": "ready",
                "steps": [{"name": "resume", "status": "skipped", "output": "valid final result already exists"}],
                "error": "",
            }
        elif audit["raw_snapshots_count"] == 0:
            result = {
                "product_slug": directory.name,
                "group_key": audit["group_key"],
                "started_at": now(), "finished_at": now(), "status": "refresh_recommended",
                "steps": [{"name": "resume", "status": "skipped", "output": "no usable local sources"}],
                "error": "no_usable_local_sources",
            }
        else:
            result = process_product(directory, group, args, statuses)
        migration["products"].append(result)
        atomic_write(MIGRATIONS / f"{directory.name}.json", result)
    if not args.dry_run:
        ok, output = run([sys.executable, str(SCRIPTS / "export_frontend_snapshot.py")])
        migration["frontend_snapshot"] = {"status": "success" if ok else "failed", "output": output}
    migration["finished_at"] = now()
    audit_after = audit_products(candidates, statuses)
    write_audit(audit_after)
    repaired_after = 0
    if args.repair_statuses and not args.dry_run:
        repaired_after = repair_statuses(audit_after, statuses)
    migration["status_repairs_after"] = repaired_after
    atomic_write(MIGRATIONS / "latest.json", migration)
    succeeded = sum(item["final_status"] == "ready" for item in audit_after)
    failed = [item["product_slug"] for item in audit_after if item["final_status"] == "analysis_failed"]
    refresh_recommended = sum(item["final_status"] == "refresh_recommended" for item in audit_after)
    snapshots_reused = sum(len(offer_ids(group)) for _, group in candidates)
    print(f"products_found={len(candidates)}")
    print(f"products_analyzed={len(migration['products'])}")
    print(f"products_succeeded={succeeded}")
    print(f"products_failed={len(failed)}")
    print(f"products_refresh_recommended={refresh_recommended}")
    print(f"status_repairs={repaired_before + repaired_after}")
    print(f"snapshots_reused={snapshots_reused}")
    print("network_fetches=0")
    print("failed_product_slugs=" + ",".join(failed))
    # A status-only repair is successful when it writes a complete audit,
    # even if that audit correctly reports older technical failures.
    return 0 if args.repair_only or not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
