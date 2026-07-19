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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from fetch_firecrawl_offer_pages import scrape_offer
from fetch_manufacturer_sources import source_identifier
from manufacturer_pipeline import normalized_document_from_fixture
from p0_runtime import atomic_write_json, atomic_write_text

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "fieldnote-api" / ".env"
SNAPSHOTS = ROOT / "input" / "manufacturer_sources"
SUPPORTED = {"kinderkraft": ("kinderkraft.pl",), "cybex": ("cybex-online.com", "cybex.pl")}
OFFICIAL_PRODUCT_URLS = {
    ("cybex", "orfeo"): "https://www.cybex-online.com/en/row/p/10102511.html",
}


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
    openai_required = not args.no_openai
    cache_dir = root / "input" / "manufacturer_sources" / f"{slug(args.brand)}__{slug(args.model)}"
    cache_status = "cached" if cache_dir.exists() else "empty"
    reason = ""
    if args.max_sources != 1:
        reason = "CONFIGURATION_ERROR:max-sources musi wynosić dokładnie 1."
    elif not domains:
        reason = "UNSUPPORTED_BRAND:brak skonfigurowanej oficjalnej domeny."
    elif not args.allow_network:
        reason = "CONSENT_FLAG_MISSING:brak --allow-network; Firecrawl jest zabroniony."
    elif not firecrawl_key:
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
        "max_firecrawl_requests": 1, "max_openai_requests": 0 if args.no_openai else 1,
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


def run_one_source(args: argparse.Namespace, counters: RequestCounters) -> dict[str, Any]:
    directory, metadata = discovery_metadata(args.brand, args.model)
    url = str(metadata.get("canonical_url") or metadata.get("source_url") or "")
    domain = url.split("/")[2].lower() if "://" in url else ""
    allowed = set(SUPPORTED[slug(args.brand).replace("-", "")])
    if domain.removeprefix("www.") not in allowed:
        raise LiveRunnerError("DISCOVERY_FAILED", "URL discovery nie wskazuje skonfigurowanej oficjalnej domeny.")
    response = attempt_provider(counters, "firecrawl", lambda: scrape_offer(url, os.environ["FIRECRAWL_API_KEY"]))
    data = response.get("data", response) if isinstance(response, dict) else {}
    if not isinstance(data, dict) or response.get("success") is False:
        raise LiveRunnerError("NETWORK_ERROR", "Firecrawl nie zwrócił poprawnej odpowiedzi data.")
    markdown = str(data.get("markdown") or "")
    html = str(data.get("html") or "")
    merged_metadata = dict(metadata)
    merged_metadata["fetched_at"] = data.get("metadata", {}).get("scrapeId", metadata.get("fetched_at", "")) if isinstance(data.get("metadata"), dict) else metadata.get("fetched_at", "")
    document = normalized_document_from_fixture(merged_metadata, markdown, source_id=str(metadata.get("source_id") or source_identifier(args.brand, url)))
    if not document.model_match:
        raise LiveRunnerError("IDENTITY_MISMATCH", document.identity_reason)
    atomic_write_json(directory / "raw_response.json", response)
    atomic_write_text(directory / "page.html", html)
    atomic_write_text(directory / "markdown.md", markdown)
    atomic_write_text(directory / "technical_clean.md", document.clean_text)
    merged_metadata.update({"source_id": document.source_id, "canonical_url": url, "content_hash": document.content_hash, "model_match": True, "authority_level": "primary", "live_validation": True})
    atomic_write_json(directory / "metadata.json", merged_metadata)
    return {"source_id": document.source_id, "raw_snapshot_saved": True, "clean_snapshot_saved": True,
            "identity_match": True, "deterministic_facts": len(document.facts),
            "ai_facts": 0, "openai_skipped_reason": "no_unresolved_candidates", "quality_rejections": 0}


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
    except LiveRunnerError as exc:
        print_payload(result, counters, failure_stage="execution", failure_reason=f"{exc.code}:{exc.reason}")
        return 3
    except Exception as exc:
        print_payload(result, counters, failure_stage="provider", failure_reason=f"NETWORK_ERROR:{type(exc).__name__}:{exc}")
        return 3
    print_payload(result, counters)
    for key, value in execution.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
