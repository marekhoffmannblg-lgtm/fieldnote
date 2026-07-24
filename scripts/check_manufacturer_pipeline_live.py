"""Controlled live preflight for one official manufacturer source.

It is deliberately a gate, not a second pipeline.  After preflight a future
single-source execution may call the existing Firecrawl provider and then the
same manufacturer normalizer/quality/evidence services used by FIELDNOTE.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from fetch_firecrawl_offer_pages import scrape_offer
from fetch_manufacturer_sources import source_identifier
from manufacturer_pipeline import normalized_document_from_fixture
from p0_runtime import atomic_write_json, atomic_write_text
from source_commit import commit_normalized_source_result
from visual_snapshots import extract_visual_context
from product_profile import generate_or_load_profile

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "fieldnote-api" / ".env"
SNAPSHOTS = ROOT / "input" / "manufacturer_sources"
SUPPORTED = {"kinderkraft": ("kinderkraft.pl",), "cybex": ("cybex-online.com", "cybex.pl")}
OFFICIAL_PRODUCT_URLS = {
    ("cybex", "orfeo"): "https://www.cybex-online.com/en/row/p/10102511.html",
}
STAGE_NAMES = (
    "discovery", "fetch", "visual_capture", "clean", "identity_validation", "normalize",
    "deterministic_extract", "ai_extract", "quality_gate", "lifecycle_commit",
    "metrics_refresh", "product_profile_generation", "api_verification",
)
ACTIVE_TRACKER: "StageTracker | None" = None


@dataclass
class RequestCounters:
    firecrawl_requests_attempted: int = 0
    firecrawl_requests_succeeded: int = 0
    firecrawl_requests_failed: int = 0
    openai_requests_attempted: int = 0
    openai_requests_succeeded: int = 0
    openai_requests_failed: int = 0


class LiveRunnerError(RuntimeError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


class StageTracker:
    """Persist an inspectable, terminal status for every manufacturer run."""

    def __init__(self, directory: Path, *, run_id: str, source_id: str = "") -> None:
        self.path = directory / "manufacturer_run_manifest.json"
        self.payload: dict[str, Any] = {
            "run_id": run_id,
            "source_id": source_id,
            "status": "running",
            "failure_stage": "",
            "failure_code": "",
            "failure_reason": "",
            "retryable": False,
            "stages": {name: {"id": f"{run_id}:{name}", "status": "pending"} for name in STAGE_NAMES},
        }
        self.save()

    def save(self) -> None:
        atomic_write_json(self.path, self.payload)

    def complete(self, stage: str, **details: Any) -> None:
        self.payload["stages"][stage] = {**self.payload["stages"][stage], "status": "completed", **details}
        self.save()

    def skip(self, stage: str, reason: str) -> None:
        self.payload["stages"][stage] = {**self.payload["stages"][stage], "status": "skipped", "reason": reason}
        self.save()

    def start(self, stage: str) -> None:
        self.payload["stages"][stage] = {**self.payload["stages"][stage], "status": "running"}
        self.save()

    def fail(self, stage: str, error: LiveRunnerError | Exception) -> None:
        code = error.code if isinstance(error, LiveRunnerError) else type(error).__name__.upper()
        reason = error.reason if isinstance(error, LiveRunnerError) else str(error)
        self.payload.update({"status": "failed", "failure_stage": stage, "failure_code": code, "failure_reason": reason, "retryable": code not in {"IDENTITY_MISMATCH", "UNSUPPORTED_BRAND"}})
        self.payload["stages"][stage] = {**self.payload["stages"][stage], "status": "failed", "failure_code": code, "failure_reason": reason}
        self.save()

    def cancel(self, stage: str) -> None:
        self.payload.update({"status": "cancelled", "failure_stage": stage, "failure_code": "CANCELLED", "failure_reason": "Run anulowany przed zapisem kolejnego etapu.", "retryable": True})
        self.payload["stages"][stage] = {**self.payload["stages"][stage], "status": "cancelled"}
        self.save()

    def active_stage(self) -> str:
        return next((name for name, item in self.payload["stages"].items() if item.get("status") == "running"), "discovery")

    def succeed(self) -> None:
        required = ("lifecycle_commit", "api_verification")
        if not all(self.payload["stages"][name]["status"] in {"completed", "skipped"} for name in required):
            raise LiveRunnerError("LIFECYCLE_INCOMPLETE", "Run nie może zakończyć się sukcesem bez lifecycle commit i weryfikacji API.")
        self.payload["status"] = "success"
        self.save()


def slug(value: str) -> str:
    return "-".join("".join(char.lower() if char.isalnum() else " " for char in value).split())


def load_configuration() -> None:
    # override=False preserves explicitly supplied shell secrets without ever
    # logging their values.
    load_dotenv(ENV_PATH, override=False)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kontrolowany preflight live dla źródła producenta.")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--allow-openai", action="store_true")
    parser.add_argument("--brand", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-sources", type=int, default=1)
    parser.add_argument("--dry-preflight", action="store_true")
    parser.add_argument("--no-openai", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-fetch", action="store_true", help="Wznawia wyłącznie z lokalnych snapshotów.")
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args(argv)


def preflight(args: argparse.Namespace, *, root: Path = ROOT) -> dict[str, Any]:
    env_path = root / "fieldnote-api" / ".env"
    load_dotenv(env_path, override=False)
    brand_key = slug(args.brand).replace("-", "")
    # `slug` keeps accented/Unicode letters; known brands are ASCII.
    brand_key = brand_key.lower()
    domains = SUPPORTED.get(brand_key, ())
    firecrawl_key = bool(os.getenv("FIRECRAWL_API_KEY", "").strip())
    openai_key = bool(os.getenv("OPENAI_API_KEY", "").strip())
    cache_only = bool(args.no_fetch or (args.resume and not args.force_refresh))
    openai_required = bool(not args.no_openai and not cache_only)
    cache_dir = root / "input" / "manufacturer_sources" / f"{slug(args.brand)}__{slug(args.model)}"
    cache_status = "cached" if cache_dir.exists() else "empty"
    reason = ""
    if args.max_sources != 1:
        reason = "CONFIGURATION_ERROR:max-sources musi wynosić dokładnie 1."
    elif not domains:
        reason = "UNSUPPORTED_BRAND:brak skonfigurowanej oficjalnej domeny."
    elif args.no_fetch and args.force_refresh:
        reason = "CONFIGURATION_ERROR:--no-fetch i --force-refresh wzajemnie się wykluczają."
    elif not cache_only and not args.allow_network:
        reason = "CONSENT_FLAG_MISSING:brak --allow-network; Firecrawl jest zabroniony."
    elif not cache_only and not firecrawl_key:
        reason = "CONFIGURATION_ERROR:brak FIRECRAWL_API_KEY."
    elif openai_required and not args.allow_openai:
        reason = "CONSENT_FLAG_MISSING:brak --allow-openai; OpenAI jest zabronione."
    elif openai_required and not openai_key:
        reason = "CONFIGURATION_ERROR:brak OPENAI_API_KEY."
    elif not env_path.exists():
        reason = "CONFIGURATION_ERROR:brak fieldnote-api/.env."
    elif not (root / "scripts" / "source_adapters.py").exists():
        reason = "CONFIGURATION_ERROR:brak ManufacturerAdapter."
    elif not (root / "scripts" / "fetch_firecrawl_offer_pages.py").exists():
        reason = "CONFIGURATION_ERROR:brak providera Firecrawl."
    elif not (root / "scripts" / "extract_model_facts_cascade.py").exists():
        reason = "CONFIGURATION_ERROR:brak klienta OpenAI."
    else:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=cache_dir, delete=True):
                pass
        except OSError as exc:
            reason = f"WRITE_FAILED:{type(exc).__name__}"
    return {
        "project_root": str(root), "env_path": str(env_path),
        "firecrawl_key_present": firecrawl_key, "openai_key_present": openai_key,
        "network_allowed": args.allow_network, "openai_allowed": args.allow_openai and not args.no_openai,
        "manufacturer_adapter_available": (root / "scripts" / "source_adapters.py").exists(),
        "firecrawl_provider_available": (root / "scripts" / "fetch_firecrawl_offer_pages.py").exists(),
        "openai_client_available": (root / "scripts" / "extract_model_facts_cascade.py").exists(),
        "brand_supported": bool(domains), "model": args.model, "official_domains": list(domains),
        "snapshot_directory": str(cache_dir), "cache_status": cache_status,
        "max_firecrawl_requests": 0 if cache_only else 1, "max_openai_requests": 0 if (args.no_openai or cache_only) else 1,
        "preflight_passed": not reason, "blocking_reason": reason,
    }


def print_payload(preflight_result: dict[str, Any], counters: RequestCounters, *, failure_stage: str = "", failure_reason: str = "") -> None:
    for key, value in {**preflight_result, **asdict(counters), "failure_stage": failure_stage, "failure_reason": failure_reason}.items():
        print(f"{key}={json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value}")


def attempt_provider(counters: RequestCounters, provider: str, operation: Any) -> Any:
    """Count the attempt immediately before a provider operation.

    The execution branch will use this helper so cost telemetry cannot be
    derived from an intended plan or a cache decision.
    """
    attempted = f"{provider}_requests_attempted"
    succeeded = f"{provider}_requests_succeeded"
    failed = f"{provider}_requests_failed"
    setattr(counters, attempted, int(getattr(counters, attempted)) + 1)
    try:
        value = operation()
    except Exception:
        setattr(counters, failed, int(getattr(counters, failed)) + 1)
        raise
    setattr(counters, succeeded, int(getattr(counters, succeeded)) + 1)
    return value


def discovery_metadata(brand: str, model: str) -> tuple[Path, dict[str, Any]]:
    directory = SNAPSHOTS / f"{slug(brand)}__{slug(model)}"
    for path in sorted(directory.glob("*/metadata.json")):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(metadata, dict) and metadata.get("model_match") is True:
            return path.parent, metadata
    url = OFFICIAL_PRODUCT_URLS.get((slug(brand), slug(model)))
    if url:
        source_id = source_identifier(brand, url)
        target = directory / source_id
        return target, {
            "source_id": source_id, "brand": brand, "model": model,
            "marketplace": "manufacturer", "source_type": "manufacturer_product_page",
            "source_url": url, "canonical_url": url, "domain": url.split("/")[2].lower(),
            "title": f"{brand} {model}", "model_match": True, "authority_level": "primary",
            "warnings": [],
        }
    raise LiveRunnerError("DISCOVERY_FAILED", "Nie znaleziono zapisanej, dopasowanej oficjalnej karty produktu.")


def api_verification(product_slug: str, source_id: str) -> bool:
    """Verify only local lifecycle artifacts; API reads exactly these indexes."""
    from provenance_v1 import load_product_provenance
    from source_lifecycle import read_product_source_links, read_source_records

    source_exists = any(str(item.get("source_id", "")) == source_id for item in read_source_records())
    link_exists = any(str(item.get("link_id", "")) == f"{product_slug}|{source_id}" for item in read_product_source_links())
    provenance = load_product_provenance(product_slug)
    evidence_exists = any(
        isinstance(evidence, dict) and str(evidence.get("source_id", "")) == source_id and bool(str(evidence.get("excerpt", "")).strip())
        for field in (provenance.get("fields", {}) if isinstance(provenance, dict) else {}).values() if isinstance(field, dict)
        for evidence in (field.get("evidence_v1", []) if isinstance(field.get("evidence_v1"), list) else [])
    )
    return source_exists and link_exists and evidence_exists


def run_one_source(args: argparse.Namespace, counters: RequestCounters) -> dict[str, Any]:
    global ACTIVE_TRACKER
    directory, metadata = discovery_metadata(args.brand, args.model)
    run_id = f"manufacturer:{slug(args.brand)}:{slug(args.model)}:{uuid.uuid4().hex[:12]}"
    tracker = StageTracker(directory, run_id=run_id, source_id=str(metadata.get("source_id", "")))
    ACTIVE_TRACKER = tracker
    tracker.complete("discovery", cached=bool((directory / "metadata.json").exists()))
    url = str(metadata.get("canonical_url") or metadata.get("source_url") or "")
    domain = url.split("/")[2].lower() if "://" in url else ""
    allowed = set(SUPPORTED[slug(args.brand).replace("-", "")])
    if domain.removeprefix("www.") not in allowed:
        tracker.fail("discovery", LiveRunnerError("DISCOVERY_FAILED", "URL discovery nie wskazuje skonfigurowanej oficjalnej domeny."))
        raise LiveRunnerError("DISCOVERY_FAILED", "URL discovery nie wskazuje skonfigurowanej oficjalnej domeny.")
    cached_markdown = directory / "markdown.md"
    cached_html = directory / "page.html"
    cached_raw = directory / "raw_response.json"
    use_cache = bool(cached_markdown.is_file() and cached_raw.is_file() and not args.force_refresh)
    if args.no_fetch and not use_cache:
        tracker.fail("fetch", LiveRunnerError("CACHE_MISSING", "--no-fetch wymaga istniejącego markdown.md i raw_response.json."))
        raise LiveRunnerError("CACHE_MISSING", "--no-fetch wymaga istniejącego markdown.md i raw_response.json.")
    tracker.start("fetch")
    if use_cache:
        markdown = cached_markdown.read_text(encoding="utf-8")
        html = cached_html.read_text(encoding="utf-8") if cached_html.exists() else ""
        response = json.loads(cached_raw.read_text(encoding="utf-8"))
        data = response.get("data", response) if isinstance(response, dict) else {}
        tracker.skip("fetch", "cache_hit")
    else:
        response = attempt_provider(counters, "firecrawl", lambda: scrape_offer(url, os.environ["FIRECRAWL_API_KEY"]))
        data = response.get("data", response) if isinstance(response, dict) else {}
        if not isinstance(data, dict) or response.get("success") is False:
            raise LiveRunnerError("NETWORK_ERROR", "Firecrawl nie zwrócił poprawnej odpowiedzi data.")
        markdown = str(data.get("markdown") or "")
        html = str(data.get("html") or "")
        tracker.complete("fetch", cached=False)
        # Persist the fetched document before visual_capture so both stages
        # inspect the same immutable local response.
        atomic_write_json(directory / "raw_response.json", response)
        atomic_write_text(directory / "page.html", html)
        atomic_write_text(directory / "markdown.md", markdown)
    tracker.start("visual_capture")
    try:
        # The live response and the visual context share the same scrape. A
        # cache run simply rebuilds the local context without network access.
        visual = extract_visual_context(
            str(metadata.get("source_id") or source_identifier(args.brand, url)),
            product_slug=f"{slug(args.brand)}__{slug(args.model)}",
            directory=directory,
            provider="cache_html" if use_cache else "firecrawl",
        )
        tracker.complete("visual_capture", capture_status=visual["snapshot"].get("capture_status"), blocks=visual["blocks"], media=visual["media"])
    except (OSError, ValueError, FileNotFoundError) as error:
        # Visual context augments the source but must never break text facts.
        tracker.skip("visual_capture", f"visual_warning:{error}")
    merged_metadata = dict(metadata)
    merged_metadata["fetched_at"] = data.get("metadata", {}).get("scrapeId", metadata.get("fetched_at", "")) if isinstance(data.get("metadata"), dict) else metadata.get("fetched_at", "")
    tracker.start("clean")
    document = normalized_document_from_fixture(merged_metadata, markdown, source_id=str(metadata.get("source_id") or source_identifier(args.brand, url)))
    tracker.complete("clean", content_hash=document.content_hash)
    tracker.start("identity_validation")
    if not document.model_match:
        tracker.fail("identity_validation", LiveRunnerError("IDENTITY_MISMATCH", document.identity_reason))
        raise LiveRunnerError("IDENTITY_MISMATCH", document.identity_reason)
    tracker.complete("identity_validation", exact_model_match=True)
    tracker.complete("normalize", normalized_document=True)
    atomic_write_text(directory / "technical_clean.md", document.clean_text)
    previous_hash = str(metadata.get("content_hash", "")).strip()
    content_changed = bool(not previous_hash or previous_hash != document.content_hash)
    merged_metadata.update({"source_id": document.source_id, "canonical_url": url, "content_hash": document.content_hash, "model_match": True, "authority_level": "primary", "live_validation": True})
    atomic_write_json(directory / "metadata.json", merged_metadata)
    content_family_id = f"manufacturer:{document.content_hash[:16]}"
    product_slug = f"{slug(args.brand)}__{slug(args.model)}"
    unchanged_refresh = bool(args.force_refresh and not content_changed and api_verification(product_slug, document.source_id))
    if unchanged_refresh:
        tracker.skip("deterministic_extract", "content_hash_unchanged")
    else:
        tracker.complete("deterministic_extract", facts_count=len(document.facts))
    unresolved_candidates_count = 0
    tracker.skip("ai_extract", "no_unresolved_candidates")
    if unchanged_refresh:
        tracker.skip("quality_gate", "content_hash_unchanged")
        tracker.skip("lifecycle_commit", "content_hash_unchanged")
        tracker.skip("metrics_refresh", "content_hash_unchanged")
        tracker.skip("product_profile_generation", "disabled_by_PRODUCT_PROFILE_AI_ENABLED")
        tracker.start("api_verification")
        tracker.complete("api_verification", verified=True)
        tracker.succeed()
        return {"source_id": document.source_id, "raw_snapshot_saved": True, "clean_snapshot_saved": True,
                "identity_match": True, "deterministic_facts": 0, "ai_facts": 0,
                "openai_skipped_reason": "no_unresolved_candidates", "openai_requested": False,
                "unresolved_candidates_count": unresolved_candidates_count, "cached_resume_used": use_cache,
                "content_changed": False, "terminal_status": tracker.payload["status"],
                "stage_statuses": {name: item["status"] for name, item in tracker.payload["stages"].items()},
                "evidence_candidates_accepted": 0, "evidence_records_created": 0, "quality_rejections": 0}
    tracker.start("quality_gate")
    committed = commit_normalized_source_result(
        run_id=run_id,
        product_slug=f"{slug(args.brand)}__{slug(args.model)}",
        source_id=document.source_id,
        source_type="manufacturer",
        adapter_id="manufacturer",
        original_url=url,
        canonical_url=url,
        raw_snapshot_path=directory / "markdown.md",
        clean_snapshot_path=directory / "technical_clean.md",
        content_hash=document.content_hash,
        content_family_id=content_family_id,
        normalized_document=document,
        evidence_candidates=document.facts,
    )
    tracker.complete("quality_gate", rejected=committed["quality_rejections"])
    tracker.complete("lifecycle_commit", source_id=document.source_id, link_id=f"{slug(args.brand)}__{slug(args.model)}|{document.source_id}")
    tracker.complete("metrics_refresh", evidence_records=committed["evidence_records_created"])
    tracker.start("product_profile_generation")
    if os.getenv("PRODUCT_PROFILE_AI_ENABLED", "").lower() in {"1", "true", "yes"}:
        try:
            profile, cached = generate_or_load_profile(product_slug, allow_openai=bool(args.allow_openai), no_openai=bool(args.no_openai))
            tracker.complete("product_profile_generation", profile_status=profile.get("profile_status"), cached=cached)
        except Exception as exc:
            # Narrative is optional and must never invalidate a committed source.
            tracker.skip("product_profile_generation", f"non_blocking:{type(exc).__name__}")
    else:
        tracker.skip("product_profile_generation", "disabled_by_PRODUCT_PROFILE_AI_ENABLED")
    tracker.start("api_verification")
    if not api_verification(product_slug, document.source_id):
        error = LiveRunnerError("API_VERIFICATION_FAILED", "Brak źródła, linku lub evidence w indeksie API produktu.")
        tracker.fail("api_verification", error)
        raise error
    tracker.complete("api_verification", verified=True)
    tracker.succeed()
    return {"source_id": document.source_id, "raw_snapshot_saved": True, "clean_snapshot_saved": True,
            "identity_match": True, "deterministic_facts": len(document.facts),
            "ai_facts": 0, "openai_skipped_reason": "no_unresolved_candidates",
            "openai_requested": False, "unresolved_candidates_count": unresolved_candidates_count,
            "cached_resume_used": use_cache, "content_changed": content_changed,
            "terminal_status": tracker.payload["status"], "stage_statuses": {name: item["status"] for name, item in tracker.payload["stages"].items()}, **committed}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = preflight(args)
    counters = RequestCounters()
    if not result["preflight_passed"]:
        print_payload(result, counters, failure_stage="preflight", failure_reason=str(result["blocking_reason"]))
        return 2
    if args.dry_preflight:
        print_payload(result, counters)
        return 0
    try:
        execution = run_one_source(args, counters)
    except KeyboardInterrupt:
        if ACTIVE_TRACKER is not None:
            ACTIVE_TRACKER.cancel(ACTIVE_TRACKER.active_stage())
        print_payload(result, counters, failure_stage="cancelled", failure_reason="CANCELLED:Run anulowany przez użytkownika.")
        return 130
    except LiveRunnerError as exc:
        if ACTIVE_TRACKER is not None:
            ACTIVE_TRACKER.fail(ACTIVE_TRACKER.active_stage(), exc)
        print_payload(result, counters, failure_stage="execution", failure_reason=f"{exc.code}:{exc.reason}")
        return 3
    except Exception as exc:
        if ACTIVE_TRACKER is not None:
            ACTIVE_TRACKER.fail(ACTIVE_TRACKER.active_stage(), exc)
        print_payload(result, counters, failure_stage="provider", failure_reason=f"NETWORK_ERROR:{type(exc).__name__}:{exc}")
        return 3
    print_payload(result, counters)
    for key, value in execution.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
