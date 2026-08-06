"""Small local API adapter for the existing FIELDNOTE Python pipeline.

This service intentionally delegates all research work to the scripts already
present in the repository.  It listens on localhost only and keeps run state
in small JSON manifests for the Vite frontend to poll.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from queue import Empty, Queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv


API_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = API_ROOT.parent
# Local credentials stay in fieldnote-api/.env. Existing process environment
# variables keep precedence, which is useful for supervised local starts.
load_dotenv(API_ROOT / ".env", override=False)
RUNS_ROOT = API_ROOT / "runs"
RUNS_ROOT.mkdir(parents=True, exist_ok=True)
PRODUCT_ANALYSIS_STATUS_PATH = PROJECT_ROOT / "output" / "product_analysis_status.json"
PRODUCT_STATE_PATH = PROJECT_ROOT / "output" / "product_state.json"
BENCHMARKS_ROOT = PROJECT_ROOT / "output" / "benchmarks"
FRONTEND_SNAPSHOT_ROOT = PROJECT_ROOT / "fieldnote-frontend" / "src" / "data" / "generated"
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from p0_runtime import (  # noqa: E402
    DEFAULT_STAGE_TIMEOUTS,
    LEASE_SECONDS,
    atomic_write_json,
    global_aggregation_lock,
    lease_until,
    process_is_alive,
)
from run_coordinator import LockUnavailableError, RunCoordinator  # noqa: E402
from run_manifest import (  # noqa: E402
    CANONICAL_RUNS_ROOT,
    RUN_STATUSES,
    index_record,
    list_manifests,
    manifest_path as canonical_manifest_path,
    read_manifest,
    rebuild_index,
    safe_run_id,
    save_manifest,
)
from source_lifecycle import (  # noqa: E402
    product_source_counters,
    read_product_source_links,
    read_source_records,
)
from benchmark_storage import (  # noqa: E402
    BenchmarkConflictError,
    BenchmarkNotFoundError,
    BenchmarkValidationError,
    create_manifest as create_competitive_benchmark_manifest,
    list_manifests as list_competitive_benchmark_manifests,
    normalized_brand as normalized_benchmark_brand,
    normalized_configuration as normalized_benchmark_configuration,
    read_manifest as read_competitive_benchmark_manifest,
)
from services.internal_benchmark_service import build_internal_benchmark  # noqa: E402
from services.competitive_benchmark_service import build_competitive_benchmark  # noqa: E402
from services.pricing_service import aggregate_prices  # noqa: E402
from visual_snapshots import artifact_id, artifact_relative, read_jsonl as read_visual_jsonl, source_visual_paths  # noqa: E402
from provenance_v1 import load_product_provenance  # noqa: E402
from product_profile import get_profile, generate_or_load_profile  # noqa: E402
from catalog_registry import (  # noqa: E402
    ensure_catalog_product,
    group_key_for,
    load_products,
    product_for_group_key,
    product_slug_for,
)
from category_registry import CategoryValidationError, categories_for_api, same_benchmark_group, supports_product_type, validate_category_assignment  # noqa: E402
from contracts import (  # noqa: E402
    CompetitiveBenchmarkCreateRequest,
    CompetitiveBenchmarkDetail,
    CompetitiveBenchmarkSummary,
    InternalBenchmarkDetail,
    InternalBenchmarkSummary,
    ProductMetricsV1,
    ProductProfileV1,
    ProductV1,
)
from repositories.snapshot_repository import SnapshotRepository  # noqa: E402
from repositories.catalog_repository import CatalogRepository  # noqa: E402
from repositories.supabase_client import SupabaseClient  # noqa: E402
from repositories.job_repository import JobRepository  # noqa: E402
from routers.health import health_payload  # noqa: E402
from routers.auth import router as auth_router  # noqa: E402
from routers.admin_users import router as admin_users_router  # noqa: E402
from auth.dependencies import require_data_write  # noqa: E402
from auth.dependencies import get_gateway  # noqa: E402
from auth.roles import Principal  # noqa: E402
from services.product_service import ProductService  # noqa: E402
from services.run_service import index_runs  # noqa: E402
from services.source_service import paginate  # noqa: E402
from services.job_service import JobService  # noqa: E402
from routers.jobs import router as jobs_router  # noqa: E402
from routers.brand_catalogs import router as brand_catalogs_router  # noqa: E402
RUN_COORDINATOR = RunCoordinator(runs_root=RUNS_ROOT, output_root=PROJECT_ROOT / "output")
DATA_MODE = os.environ.get("FIELDNOTE_DATA_MODE", "legacy_readonly")
if DATA_MODE not in {"legacy_readonly", "supabase"}:
    raise RuntimeError("FIELDNOTE_DATA_MODE must be legacy_readonly or supabase.")
PRODUCT_SERVICE = ProductService(
    CatalogRepository(SupabaseClient.from_env()) if DATA_MODE == "supabase" else SnapshotRepository(FRONTEND_SNAPSHOT_ROOT)
)
LOCAL_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
)
MAX_LOG_LINES = 240
MAX_LOG_CHARS = 18_000
RUN_TIMEOUT_SECONDS = DEFAULT_STAGE_TIMEOUTS["pipeline"]
CONTROLLED_SOURCE_ANALYSIS_EXIT = 20
SOURCE_ANALYSIS_TIMEOUT_MESSAGE = "Analiza źródła przekroczyła limit czasu. Zachowano dotychczasowe dane."
LABEL_PATTERN = re.compile(r"^[0-9A-Za-z²³ĄĆĘŁŃÓŚŹŻąćęłńóśźż .,'&()/-]{1,80}$")
OFFER_ID_PATTERN = re.compile(r"^\d{6,20}$")
PRODUCT_SLUG_PATTERN = re.compile(r"^[a-z0-9]+__[a-z0-9-]+$")
ACCESSORY_TERMS = (
    "spiworek", "palak", "barierka", "bumper bar", "bumperbar", "adapter", "torba",
    "folia", "moskitiera", "uchwyt", "wkladka", "organizer", "pokrowiec",
    "czesc zamienna", "czesci zamienne", "zestaw transportowy",
)
STROLLER_TERMS = ("wozek", "spacerowka", "stroller", "buggy")
SECRET_PATTERN = re.compile(r"(?i)(firecrawl_api_key|openai_api_key|authorization)\s*[:=]\s*\S+")
PIPELINE_SECRET_KEYS = ("OPENAI_API_KEY", "FIRECRAWL_API_KEY")
INVALID_SELLER_LABELS = {
    "gwarancji", "gwarancja", "dostawa", "kup teraz", "stan", "zwrot", "zwroty",
    "platnosc", "platnosci", "opis", "parametry", "sprzedawca", "oferta",
}


class RunCancelledError(RuntimeError):
    """Raised inside a worker after the user requested cancellation."""


app = FastAPI(title="FIELDNOTE Local API", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(LOCAL_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(jobs_router)
app.include_router(brand_catalogs_router)
if DATA_MODE == "supabase":
    _job_client = SupabaseClient.from_env()
    app.state.job_service = JobService(JobRepository(_job_client), CatalogRepository(_job_client))

@app.middleware("http")
async def supabase_api_guard(request: Request, call_next: Any) -> Any:
    if DATA_MODE != "supabase" or not request.url.path.startswith("/api/") or request.url.path in {"/api/health"} or request.url.path.startswith("/api/auth/"):
        return await call_next(request)
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"detail": "Wymagane logowanie."})
    try:
        principal = get_gateway().principal(authorization.split(" ", 1)[1])
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if principal.must_change_password:
        return JSONResponse(status_code=403, content={"detail": {"code": "INITIAL_PASSWORD_CHANGE_REQUIRED"}})
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and principal.role not in {"analyst", "admin"}:
        return JSONResponse(status_code=403, content={"detail": "Brak uprawnień."})
    request.state.principal = principal
    return await call_next(request)


@app.get("/api/categories")
def category_options() -> dict[str, Any]:
    """Expose the one canonical category registry to the local frontend."""
    return {"categories": categories_for_api()}


class PreviewRequest(BaseModel):
    brand: str
    model: str
    marketplace: Literal["allegro"] = "allegro"
    previous_product_slug: str | None = None
    category_key: str = ""
    benchmark_group: str = ""
    search_mode: Literal["live", "cache"] = "live"

    @field_validator("brand", "model")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return validated_label(value)


class ProductCreateRequest(BaseModel):
    """Register product identity before any preview or source collection."""

    brand: str
    model: str
    category_key: str
    benchmark_group: str

    @field_validator("brand", "model")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return validated_label(value)

    @field_validator("category_key", "benchmark_group")
    @classmethod
    def validate_category_tokens(cls, value: str) -> str:
        return str(value or "").strip()


class ResearchRequest(BaseModel):
    brand: str
    model: str
    selected_offer_ids: list[str] = Field(default_factory=list, max_length=100)
    selected_manufacturer_source_ids: list[str] = Field(default_factory=list, max_length=10)
    include_manufacturer_sources: bool = True
    category_key: str = ""
    benchmark_group: str = ""

    @field_validator("brand", "model")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return validated_label(value)

    @field_validator("selected_offer_ids")
    @classmethod
    def validate_offer_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            offer_id = str(value).strip()
            if not OFFER_ID_PATTERN.fullmatch(offer_id):
                raise ValueError("Każdy identyfikator oferty musi składać się wyłącznie z cyfr.")
            if offer_id not in normalized:
                normalized.append(offer_id)
        return normalized

    @field_validator("category_key", "benchmark_group")
    @classmethod
    def validate_category_tokens(cls, value: str) -> str:
        return str(value or "").strip()


class RefreshRequest(BaseModel):
    mode: Literal["incremental", "full_reanalysis"] = "incremental"


class AnalysisRequest(BaseModel):
    """Run analysis from persisted local source snapshots."""

    refresh_sources: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.translate(str.maketrans({"ł": "l", "Ł": "L"}))
    return re.sub(r"\s+", " ", text.lower()).strip()


def path_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalized(value)).strip("-")
    return slug or "model"


def preview_cache_key(marketplace: str, brand: str, model: str, category_key: str) -> str:
    """Keep previews isolated by marketplace and the complete requested model."""
    return f"{normalized(marketplace)}|{path_slug(brand)}|{path_slug(model)}|{str(category_key or '').strip()}"


def validated_label(value: str) -> str:
    clean = " ".join(str(value).split()).strip()
    if not LABEL_PATTERN.fullmatch(clean) or ".." in clean or "/" in clean or "\\" in clean:
        raise ValueError("Dozwolone są wyłącznie krótka nazwa marki lub modelu bez znaków ścieżki.")
    return clean


def redact(value: str) -> str:
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[ukryte]", value)


def run_path(run_id: str) -> Path:
    try:
        safe_run_id(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Nie znaleziono uruchomienia.")
    return canonical_manifest_path(run_id)


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def persist_canonical_context(run_id: str, context: dict[str, Any], payload: dict[str, Any]) -> None:
    """Store the immutable context in the same directory as its manifest."""
    path = CANONICAL_RUNS_ROOT / safe_run_id(run_id) / "context.json"
    atomic_write_json(path, context)
    payload["context_path"] = str(path.relative_to(PROJECT_ROOT))


def read_run(run_id: str) -> dict[str, Any]:
    try:
        value = read_manifest(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Nie znaleziono zapisu uruchomienia.") from exc
    if value is not None:
        return normalize_terminal_run_status(value)
    # Read-only compatibility for legacy API manifests. Migration preserves the
    # source file but all new writes immediately use output/runs/<id>/.
    legacy_path = RUNS_ROOT / f"{run_id}.json"
    value = read_json(legacy_path, {})
    if isinstance(value, dict) and value:
        return normalize_terminal_run_status(value)
    raise HTTPException(status_code=404, detail="Nie znaleziono zapisu uruchomienia.")


def save_run(payload: dict[str, Any]) -> None:
    normalize_terminal_run_status(payload)
    payload["updated_at"] = utc_now()
    payload["created_at"] = payload.get("created_at") or payload.get("started_at") or utc_now()
    # P0 fixture compatibility: isolated tests replace RUNS_ROOT with a
    # temporary legacy directory. Production keeps this path unchanged and
    # writes only the canonical manifest in output/runs.
    if RUNS_ROOT != API_ROOT / "runs":
        atomic_write_json(RUNS_ROOT / f"{payload['run_id']}.json", payload)
        return
    save_manifest(payload)


def normalize_terminal_run_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep the public status aligned with pipeline_status for terminal partial runs."""
    if payload.get("pipeline_status") == "partial":
        payload["status"] = "partial"
    elif payload.get("pipeline_status") == "failed" and payload.get("status") == "succeeded":
        payload["status"] = "failed"
    return payload


def run_response(payload: dict[str, Any]) -> dict[str, Any]:
    logs = payload.get("logs", [])
    if not isinstance(logs, list):
        logs = []
    return {
        "run_id": payload.get("run_id", ""),
        "status": payload.get("status", "failed"),
        "current_step": payload.get("current_step", ""),
        "progress": payload.get("progress", 0),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "error": payload.get("error", ""),
        "logs_tail": logs[-80:],
        "product_slug": payload.get("product_slug", ""),
        "snapshot_updated": bool(payload.get("snapshot_updated", False)),
        "refresh": payload.get("refresh", {}),
        "analysis": payload.get("analysis", {}),
        "pipeline_status": payload.get("pipeline_status", ""),
        "last_heartbeat_at": payload.get("last_heartbeat_at"),
        "lease_expires_at": payload.get("lease_expires_at"),
        "child_pid": payload.get("child_pid"),
        "cancel_requested_at": payload.get("cancel_requested_at"),
        "run_type": payload.get("run_type", "research"),
        "retry_of": payload.get("retry_of"),
        "created_at": payload.get("created_at"),
        "sources_selected": payload.get("sources_selected", len(payload.get("selected_offer_ids", []))),
        "sources_fetched": payload.get("sources_fetched", 0),
        "sources_failed": payload.get("sources_failed", 0),
        "sources_attached": payload.get("sources_attached", 0),
        "coverage_before": payload.get("coverage_before"),
        "coverage_after": payload.get("coverage_after"),
        "changed_fields": payload.get("changed_fields", []),
        "product_profile_stage": payload.get("product_profile_stage", ""),
        "product_profile_status": payload.get("product_profile_status", ""),
        "product_profile_warning": payload.get("product_profile_warning", ""),
    }


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def default_product_state(product_slug: str) -> dict[str, Any]:
    return {
        "product_slug": product_slug,
        "result_status": "none",
        "active_run_status": "none",
        "last_successful_run_id": None,
        "last_failed_run_id": None,
        "last_successful_at": None,
        "last_failed_at": None,
        "refresh_recommended": False,
        "refresh_reason": None,
        "updated_at": utc_now(),
    }


def load_product_states() -> dict[str, dict[str, Any]]:
    value = read_json(PRODUCT_STATE_PATH, {})
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(item, dict)}


def public_product_status(state: dict[str, Any]) -> str:
    if str(state.get("active_run_status", "none")) in {"queued", "running"}:
        return "analysis_running"
    if state.get("result_status") == "ready":
        return "refresh_recommended" if bool(state.get("refresh_recommended")) else "ready"
    if state.get("last_failed_run_id"):
        return "analysis_failed"
    # Existing products with saved sources but no final analysis are actionable,
    # not broken. This avoids reintroducing legacy waiting/pending statuses.
    return "refresh_recommended"


def update_product_state(
    product_slug: str,
    event: str,
    *,
    run_id: str | None = None,
    error: str = "",
    refresh_reason: str | None = None,
) -> dict[str, Any]:
    """Apply canonical lifecycle precedence while preserving earlier results."""
    states = load_product_states()
    state = {**default_product_state(product_slug), **states.get(product_slug, {})}
    now = utc_now()
    if event in {"queued", "running"}:
        state["active_run_status"] = event
    elif event == "succeeded":
        state.update({
            "result_status": "ready",
            "active_run_status": "none",
            "last_successful_run_id": run_id or state.get("last_successful_run_id"),
            "last_successful_at": now,
            "refresh_recommended": False,
            "refresh_reason": None,
        })
    elif event in {"failed", "timed_out", "cancelled", "interrupted"}:
        state.update({
            "active_run_status": "none",
            "last_failed_run_id": run_id or state.get("last_failed_run_id"),
            "last_failed_at": now,
        })
        if state.get("result_status") == "ready":
            state["refresh_recommended"] = True
            state["refresh_reason"] = refresh_reason or error or "Ostatni refresh nie zakończył się poprawnie."
        else:
            state["result_status"] = "invalid"
    elif event == "refresh_recommended":
        state["active_run_status"] = "none"
        if state.get("result_status") == "none":
            state["result_status"] = "ready" if state.get("last_successful_run_id") else "none"
        state["refresh_recommended"] = True
        state["refresh_reason"] = refresh_reason or error or "Dane wymagają odświeżenia."
    state["updated_at"] = now
    states[product_slug] = state
    atomic_write_json(PRODUCT_STATE_PATH, states)

    # Preserve the legacy read path as a derived compatibility projection.
    legacy = read_json(PRODUCT_ANALYSIS_STATUS_PATH, {})
    legacy = legacy if isinstance(legacy, dict) else {}
    try:
        canonical_path = str(PRODUCT_STATE_PATH.relative_to(PROJECT_ROOT))
    except ValueError:
        canonical_path = str(PRODUCT_STATE_PATH)
    legacy[product_slug] = {
        "status": public_product_status(state),
        "updated_at": now,
        "error": error,
        "canonical_state_path": canonical_path,
    }
    atomic_write_json(PRODUCT_ANALYSIS_STATUS_PATH, legacy)
    return state


def set_product_analysis_status(product_slug: str, status: str, *, error: str = "", run_id: str | None = None) -> None:
    """Compatibility wrapper for older workers, now backed by canonical state."""
    event = {
        "analysis_running": "running",
        "ready": "succeeded",
        "analysis_failed": "failed",
        "refresh_recommended": "refresh_recommended",
    }.get(status, status)
    update_product_state(product_slug, event, run_id=run_id, error=error)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        value = read_json_from_string(line)
        if isinstance(value, dict):
            records.append(value)
    return records


def read_json_from_string(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def load_price_by_offer_id() -> dict[str, str]:
    rows: dict[str, str] = {}
    path = PROJECT_ROOT / "output" / "firecrawl_offer_urls.csv"
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            offer_id = str(row.get("offer_id", "")).strip()
            price = str(row.get("price", "")).strip()
            if offer_id and price:
                rows[offer_id] = price
    return rows


def known_offer_data() -> dict[str, dict[str, str]]:
    registry = read_jsonl(PROJECT_ROOT / "output" / "source_registry.jsonl")
    prices = load_price_by_offer_id()
    offers: dict[str, dict[str, str]] = {}
    for row in registry:
        offer_id = str(row.get("external_offer_id", "")).strip()
        if not offer_id:
            continue
        offers[offer_id] = {
            "seller": str(row.get("seller_name", "")).strip(),
            "price": prices.get(offer_id, ""),
        }
    return offers


def targeted_dir(brand: str, model: str, marketplace: str = "allegro") -> Path:
    root = PROJECT_ROOT / "input" / "targeted_search"
    canonical = root / f"{path_slug(brand)}__{path_slug(model)}" / marketplace
    # Earlier local listings used a lossy ASCII slug. Read them once as cache
    # input; the fetcher now writes the canonical NFKD path on the next run.
    legacy_slug = lambda value: re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "model"
    legacy = root / f"{legacy_slug(brand)}__{legacy_slug(model)}" / marketplace
    if not canonical.exists() and legacy.exists():
        return legacy
    return canonical


def canonical_targeted_dir(brand: str, model: str, marketplace: str = "allegro") -> Path:
    """Write path for new searches; it never falls back to legacy cache."""
    return PROJECT_ROOT / "input" / "targeted_search" / f"{path_slug(brand)}__{path_slug(model)}" / marketplace


def listing_cache_dir(brand: str, model: str, marketplace: str, category_key: str) -> Path:
    return canonical_targeted_dir(brand, model, marketplace) / "search_cache" / path_slug(category_key)


def cache_metadata_path(directory: Path) -> Path:
    return directory / "search_cache_metadata.json"


def iso_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def cached_listing_info(brand: str, model: str, marketplace: str, category_key: str) -> dict[str, Any] | None:
    """Find a category-scoped cache first, then legacy cache only for cache mode."""
    primary = listing_cache_dir(brand, model, marketplace, category_key)
    candidates = [(primary, False), (targeted_dir(brand, model, marketplace), True)]
    for directory, legacy in candidates:
        listing = directory / "listing.html"
        if not listing.is_file():
            continue
        metadata = read_json(cache_metadata_path(directory), {})
        fetched_at = str(metadata.get("fetched_at", "") or iso_from_mtime(listing)) if isinstance(metadata, dict) else iso_from_mtime(listing)
        return {"directory": directory, "legacy": legacy, "cached_at": fetched_at}
    return None


def cache_listing_artifacts(source: Path, destination: Path, *, marketplace: str, brand: str, model: str, category_key: str, fetched_at: str | None = None) -> str:
    """Persist only listing-search artifacts under the category-aware cache key."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("listing.html", "listing.md", "raw_response.json", "metadata.json", "extracted_offers.json", "rejected_offers.json", "research_summary.json"):
        path = source / name
        if path.is_file():
            shutil.copy2(path, destination / name)
    fetched_at = fetched_at or utc_now()
    atomic_write_json(cache_metadata_path(destination), {
        "marketplace": marketplace,
        "brand": brand,
        "model": model,
        "category_key": category_key,
        "fetched_at": fetched_at,
        "cache_key": preview_cache_key(marketplace, brand, model, category_key),
        "schema_version": "1",
    })
    return fetched_at


def nullable_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def product_type_for_preview(title: str) -> str:
    text = normalized(title)
    if not text:
        return "unknown"
    has_stroller = any(re.search(rf"\b{re.escape(term)}\b", text) for term in STROLLER_TERMS)
    has_accessory = any(term in text for term in ACCESSORY_TERMS)
    if has_stroller:
        return "stroller"
    if has_accessory:
        return "accessory"
    return "unknown"


def price_amount(value: str | None) -> float | None:
    match = re.search(r"(\d[\d .]*)\s*,\s*(\d{2})\s*(?:zł|pln)\b", value or "", re.I)
    if not match:
        return None
    try:
        return float(f"{match.group(1).replace(' ', '').replace('.', '')}.{match.group(2)}")
    except ValueError:
        return None


def title_completeness(title: str, brand: str, model: str) -> int:
    tokens = re.findall(r"[\wÀ-ž]+", normalized(title))
    model_tokens = re.findall(r"[\wÀ-ž]+", normalized(model))
    has_brand = normalized(brand) in tokens
    has_model = bool(model_tokens) and all(token in tokens for token in model_tokens)
    return int(has_brand) + int(has_model) + int(len(tokens) >= 5)


def offer_quality(
    offer: dict[str, Any],
    *,
    brand: str,
    model: str,
    median_price: float | None,
) -> dict[str, Any]:
    """Score only evidence available in the listing card; missing data is neutral."""
    score = 0
    reasons: list[str] = []
    exact_match = bool(offer.get("accepted"))
    is_accessory = bool(offer.get("is_accessory"))
    completeness = title_completeness(str(offer.get("title", "")), brand, model)

    if exact_match:
        score += 50
        reasons.append("dokładne dopasowanie marki i modelu")
    else:
        reasons.append("brak dokładnego dopasowania modelu")

    if completeness == 3:
        score += 25
        reasons.append("kompletny tytuł oferty")
    elif completeness >= 1:
        score += 10
        reasons.append("częściowo kompletny tytuł")

    price = price_amount(nullable_text(offer.get("price")))
    if price is not None:
        score += 5
        reasons.append("cena dostępna w listingu")
        if median_price and abs(price - median_price) / median_price > 0.45:
            score -= 10
            reasons.append("cena wyraźnie odstaje od mediany dopasowanych ofert")

    seller_rating = offer.get("seller_rating")
    seller_reviews = offer.get("seller_reviews_count")
    try:
        if seller_rating is not None and float(str(seller_rating).replace(",", ".").replace("%", "")) >= 90:
            score += 5
            reasons.append("wysoka ocena sprzedawcy potwierdzona w listingu")
    except ValueError:
        pass
    try:
        if seller_reviews is not None and int(str(seller_reviews).replace(" ", "")) >= 10:
            score += 5
            reasons.append("liczba opinii sprzedawcy potwierdzona w listingu")
    except ValueError:
        pass

    seller_type = normalized(str(offer.get("seller_type") or ""))
    if seller_type in {"oficjalny sklep", "sklep firmowy", "firma"}:
        score += 5
        reasons.append("potwierdzony sklep firmowy lub oficjalny")

    duplicate_count = int(offer.get("duplicate_count") or 0)
    if duplicate_count:
        score -= min(20, duplicate_count * 10)
        reasons.append("powtórzenie tej samej oferty w listingu")

    if is_accessory:
        score -= 60
        reasons.append("akcesorium lub część nie jest ofertą produktu")

    score = max(0, min(100, score))
    level = "high" if score >= 80 else "medium" if score >= 50 else "low"
    return {"score": score, "level": level, "reasons": reasons}


def has_typical_price(value: str | None, median_price: float | None) -> bool:
    price = price_amount(value)
    if price is None:
        return False
    return not median_price or abs(price - median_price) / median_price <= 0.45


def read_preview_offers(brand: str, model: str, category_key: str, *, directory: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    directory = directory or targeted_dir(brand, model)
    accepted_records = read_json(directory / "extracted_offers.json", [])
    rejected_records = read_json(directory / "rejected_offers.json", [])
    summary = read_json(directory / "research_summary.json", {})
    if not isinstance(accepted_records, list):
        accepted_records = []
    if not isinstance(rejected_records, list):
        rejected_records = []
    offers: list[dict[str, Any]] = []
    for raw in [*accepted_records, *rejected_records]:
        if not isinstance(raw, dict):
            continue
        offer_id = str(raw.get("offer_id", "")).strip()
        if not offer_id:
            continue
        title = str(raw.get("title", "")).strip()
        raw_product_type = str(raw.get("product_type", ""))
        product_type = raw_product_type if raw_product_type in {"stroller", "accessory", "unknown"} else product_type_for_preview(title)
        brand_match = bool(raw.get("brand_match", False))
        model_match = bool(raw.get("model_match", False))
        is_accessory = product_type == "accessory"
        category_compatible = supports_product_type(category_key, product_type)
        raw_status = str(raw.get("match_status", "")).strip()
        is_accepted = bool(brand_match and model_match and category_compatible and not is_accessory)
        if product_type == "accessory":
            match_status = "rejected"
        elif is_accepted:
            match_status = "exact_match"
        elif raw_status == "probable_match" and brand_match and category_compatible and not is_accessory:
            match_status = "probable_match"
        elif brand_match and model_match and product_type != "accessory":
            match_status = "probable_match"
        else:
            match_status = "rejected"
        offers.append(
            {
                "offer_id": offer_id,
                "title": title,
                "url": str(raw.get("canonical_url", "")).strip(),
                "seller_name": nullable_text(raw.get("seller_name")),
                "seller_type": nullable_text(raw.get("seller_type")),
                "seller_rating": raw.get("seller_rating") if raw.get("seller_rating") is not None else None,
                "seller_reviews_count": raw.get("seller_reviews_count") if raw.get("seller_reviews_count") is not None else None,
                "price": nullable_text(raw.get("price")),
                "currency": nullable_text(raw.get("currency")),
                "condition": nullable_text(raw.get("condition")),
                "sponsored": raw.get("sponsored") if isinstance(raw.get("sponsored"), bool) else None,
                "brand_match": brand_match,
                "model_match": model_match,
                "accepted": is_accepted,
                "already_known": bool(raw.get("already_known", False)),
                "is_accessory": is_accessory,
                "product_type": product_type,
                "product_type_label": (
                    "Produkt zgodny z kategorią" if category_compatible
                    else "Akcesorium" if is_accessory
                    else "Typ niezgodny lub nieustalony"
                ),
                "category_compatible": category_compatible,
                "match_status": match_status,
                "selectable": match_status in {"exact_match", "probable_match"},
                "rejection_reason": str(raw.get("rejection_reason", "")).strip() or None,
                "duplicate_count": int(raw.get("duplicate_count") or 0),
            }
        )

    exact_prices = [price_amount(offer.get("price")) for offer in offers if offer.get("accepted")]
    numeric_prices = [price for price in exact_prices if price is not None]
    median_price = statistics.median(numeric_prices) if numeric_prices else None
    for offer in offers:
        offer["offer_quality"] = offer_quality(offer, brand=brand, model=model, median_price=median_price)
    offers.sort(
        key=lambda offer: (
            bool(offer.get("accepted")),
            title_completeness(str(offer.get("title", "")), brand, model),
            has_typical_price(offer.get("price"), median_price),
            not bool(offer.get("duplicate_count")),
            int(offer["offer_quality"]["score"]),
        ),
        reverse=True,
    )
    exact_matches = [offer for offer in offers if offer.get("match_status") == "exact_match"]
    for index, offer in enumerate(exact_matches):
        offer["source_group"] = "primary_source" if index < 10 else "supplementary_source"
    for offer in offers:
        offer.setdefault("source_group", None)
    return offers, summary if isinstance(summary, dict) else {}


def manufacturer_sources_for(brand: str, model: str) -> list[dict[str, Any]]:
    """Read local official sources only; this helper never calls the network."""
    group_dir = PROJECT_ROOT / "output" / "model_groups" / f"{path_slug(brand)}__{path_slug(model)}"
    group = read_json(group_dir / "group.json", {})
    registry = {str(item.get("source_id", "")): item for item in read_jsonl(PROJECT_ROOT / "output" / "source_registry.jsonl")}
    lifecycle_records = {str(item.get("source_id", "")): item for item in read_source_records()}
    candidates: dict[str, dict[str, Any]] = {}
    for group_source in group.get("sources", []) if isinstance(group.get("sources"), list) else []:
        if isinstance(group_source, dict):
            source_id = str(group_source.get("source_id", ""))
            candidates[source_id] = {**group_source, **registry.get(source_id, {}), **lifecycle_records.get(source_id, {})}
    for source_id, source in lifecycle_records.items():
        if (
            str(source.get("marketplace", "")) == "manufacturer"
            and normalized(str(source.get("brand", ""))) == normalized(brand)
            and normalized(str(source.get("model", ""))) == normalized(model)
        ):
            candidates[source_id] = {**registry.get(source_id, {}), **source}
    sources: list[dict[str, Any]] = []
    for source_id, source in candidates.items():
        if source.get("marketplace") != "manufacturer":
            continue
        content = source.get("content", {}) if isinstance(source.get("content"), dict) else {}
        snapshot = str(content.get("clean_snapshot_path") or content.get("raw_snapshot_path") or source.get("manufacturer_source_path", ""))
        metadata_path = PROJECT_ROOT / snapshot
        metadata = read_json((metadata_path.parent if metadata_path.suffix else metadata_path) / "metadata.json", {})
        model_match = metadata.get("model_match") is True
        raw, clean = local_source_files({**source, "manufacturer_source_path": str(metadata_path.parent)})
        available = bool(raw or clean)
        if available and model_match:
            match_status = "matched"
        elif available:
            match_status = "uncertain"
        else:
            match_status = "unavailable"
        source_type = str(source.get("source_type", "manufacturer_product_page"))
        if source_type == "manufacturer":
            source_type = str(metadata.get("source_type", "manufacturer_product_page"))
        type_label = {
            "manufacturer_product_page": "Strona produktu",
            "manufacturer_manual_pdf": "Instrukcja PDF",
            "manufacturer_support_page": "Strona wsparcia",
        }.get(source_type, source_type)
        url = str(source.get("canonical_url") or source.get("source_url") or "")
        sources.append({
            "source_id": source_id,
            "title": str(source.get("title") or metadata.get("title") or "Oficjalne źródło producenta"),
            "source_type": source_type,
            "type_label": type_label,
            "domain": str(source.get("domain") or urlparse(url).netloc.lower()),
            "url": url,
            "model_match": model_match,
            "match_status": match_status,
            "fetch_status": str((source.get("fetch", {}) if isinstance(source.get("fetch"), dict) else {}).get("status", "unchecked")),
            "clean_status": str((source.get("cleaning", {}) if isinstance(source.get("cleaning"), dict) else {}).get("status", "not_started")),
            "cached": available,
            "last_fetched_at": str((source.get("fetch", {}) if isinstance(source.get("fetch"), dict) else {}).get("fetched_at", metadata.get("fetched_at", ""))),
            "refresh_recommended": False,
        })
    return sources


def pipeline_environment() -> dict[str, str]:
    """Return a subprocess environment without ever serialising secret values."""
    environment = os.environ.copy()
    for key in PIPELINE_SECRET_KEYS:
        value = os.getenv(key)
        if value:
            environment[key] = value
        else:
            environment.pop(key, None)
    return environment


def run_command(
    command: list[str], *, cwd: Path = PROJECT_ROOT, timeout: int = RUN_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=pipeline_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )


def validated_product_slug(product_slug: str, *, require_group: bool = True) -> str:
    if not PRODUCT_SLUG_PATTERN.fullmatch(product_slug):
        raise HTTPException(status_code=404, detail="Nie znaleziono produktu.")
    if DATA_MODE == "supabase":
        return product_slug
    group_dir = PROJECT_ROOT / "output" / "model_groups" / product_slug
    if require_group:
        registered = any(product_slug_for(item.get("brand", ""), item.get("model", "")) == product_slug for item in load_products())
        if registered:
            return product_slug
    if require_group and not (group_dir / "group.json").is_file():
        raise HTTPException(status_code=404, detail="Nie znaleziono grupy produktu.")
    return product_slug


def group_dir_for_slug(product_slug: str) -> Path:
    return PROJECT_ROOT / "output" / "model_groups" / validated_product_slug(product_slug)


def coverage_for_group(group_key: str) -> float | None:
    path = PROJECT_ROOT / "output" / "model_coverage.csv"
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("group_key") != group_key:
                continue
            try:
                return float(str(row.get("coverage_percent", "")).replace(",", "."))
            except ValueError:
                return None
    return None


def has_valid_final_result(group_key: str, fields: dict[str, Any]) -> bool:
    """A usable benchmark row wins over a later failed maintenance run."""
    if not fields or coverage_for_group(group_key) is None:
        return False
    path = PROJECT_ROOT / "output" / "model_benchmark.csv"
    if not path.exists():
        return False
    with path.open(encoding="utf-8", newline="") as handle:
        return any(row.get("group_key") == group_key for row in csv.DictReader(handle))


def hash_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def local_source_files(source: dict[str, Any]) -> tuple[Path | None, Path | None]:
    content = str(source.get("content_path", "") or "")
    manufacturer = str(source.get("manufacturer_source_path", "") or "")
    sections = str(source.get("offer_sections_path", "") or "")
    clean_candidates: list[Path] = []
    raw_candidates: list[Path] = []
    if content:
        clean = PROJECT_ROOT / content
        clean_candidates.append(clean)
        raw_candidates.append(clean.parent / "markdown.md")
    if manufacturer:
        directory = PROJECT_ROOT / manufacturer
        clean_candidates.append(directory / "technical_clean.md")
        raw_candidates.append(directory / "markdown.md")
    if sections:
        directory = (PROJECT_ROOT / sections).parent
        clean_candidates.append(directory / "technical_clean.md")
        raw_candidates.append(directory / "markdown.md")
    clean = next((path for path in clean_candidates if path.is_file()), None)
    raw = next((path for path in raw_candidates if path.is_file()), None)
    return raw, clean


def read_csv_by_offer_id(path: Path) -> dict[str, dict[str, str]]:
    """Read a local offer export without assuming every optional column exists."""
    rows: dict[str, dict[str, str]] = {}
    if not path.exists():
        return rows
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                offer_id = str(row.get("offer_id", "")).strip()
                if offer_id:
                    rows[offer_id] = {key: str(value or "").strip() for key, value in row.items()}
    except OSError:
        return rows
    return rows


def queue_rows_by_offer_id() -> dict[str, dict[str, str]]:
    return read_csv_by_offer_id(PROJECT_ROOT / "output" / "firecrawl_offer_queue.csv")


def offer_rows_by_offer_id() -> dict[str, dict[str, str]]:
    """Prefer the dedicated Firecrawl export and enrich it from market listings."""
    rows = read_csv_by_offer_id(PROJECT_ROOT / "output" / "market_offers.csv")
    rows.update(read_csv_by_offer_id(PROJECT_ROOT / "output" / "firecrawl_offer_urls.csv"))
    return rows


def evidence_entries(value: Any) -> list[dict[str, Any]]:
    """Accept legacy evidence shapes but attribute only structured provenance."""
    if value is None or value == "":
        return []
    items = value if isinstance(value, list) else [value]
    return [item for item in items if isinstance(item, dict)]


def source_evidence_index(state: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Index exactly the fields that name a source_id in model-state evidence."""
    index: dict[str, list[dict[str, str]]] = {}
    fields = state.get("fields", {}) if isinstance(state, dict) else {}
    if not isinstance(fields, dict):
        return index
    for field_name, raw_field in fields.items():
        field = raw_field if isinstance(raw_field, dict) else {}
        field_value = str(field.get("value", "X") or "X")
        for item in evidence_entries(field.get("evidence")):
            source_id = str(item.get("source_id", "")).strip()
            excerpt = str(item.get("evidence", "")).strip()
            if not source_id or not excerpt:
                continue
            index.setdefault(source_id, []).append(
                {
                    "field_name": str(field_name),
                    "value": str(item.get("value", field_value) or field_value),
                    "excerpt": excerpt[:300],
                }
            )
    return index


def source_contribution_index(state: dict[str, Any]) -> dict[str, dict[str, list[dict[str, str]]]]:
    """Classify each persisted evidence item by its contribution to final fields.

    The state contains the accepted evidence that survived deterministic
    validation. The first evidence agreeing with the final value introduces a
    field; later agreeing evidence confirms it. Different saved values are
    presented as conflicts, never as additional new fields.
    """
    result: dict[str, dict[str, list[dict[str, str]]]] = {}
    fields = state.get("fields", {}) if isinstance(state, dict) else {}
    if not isinstance(fields, dict):
        return result

    def bucket(source_id: str) -> dict[str, list[dict[str, str]]]:
        return result.setdefault(source_id, {
            "unique_fields_contributed": [],
            "confirmed_fields": [],
            "conflicting_fields": [],
            "rejected_evidence": [],
            "final_fields_used": [],
        })

    for field_name, raw in fields.items():
        if not isinstance(raw, dict):
            continue
        final_value = str(raw.get("value", "X") or "X")
        accepted_first = False
        for evidence in evidence_entries(raw.get("evidence")):
            source_id = str(evidence.get("source_id", "")).strip()
            excerpt = str(evidence.get("evidence", "")).strip()
            if not source_id or not excerpt:
                continue
            value = str(evidence.get("value", final_value) or final_value)
            item = {"field_name": str(field_name), "value": value, "excerpt": excerpt[:300]}
            target = bucket(source_id)
            if final_value == "X" or normalized(value) != normalized(final_value):
                target["conflicting_fields"].append(item)
            elif not accepted_first:
                target["unique_fields_contributed"].append(item)
                target["final_fields_used"].append(item)
                accepted_first = True
            else:
                target["confirmed_fields"].append(item)
                target["final_fields_used"].append(item)
        # Future validators may persist rejected evidence. Keep it visible when
        # provenance is available, but never invent rejected evidence.
        for evidence in evidence_entries(raw.get("rejected_evidence")):
            source_id = str(evidence.get("source_id", "")).strip()
            excerpt = str(evidence.get("evidence", "")).strip()
            if source_id and excerpt:
                bucket(source_id)["rejected_evidence"].append({
                    "field_name": str(field_name),
                    "value": str(evidence.get("value", "X") or "X"),
                    "excerpt": excerpt[:300],
                })
    return result


def relative_snapshot_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return ""


def source_role(source: dict[str, Any], evidence_fields: list[dict[str, str]]) -> str:
    if str(source.get("marketplace", "")).strip() == "manufacturer":
        return "manufacturer"
    return "primary" if evidence_fields else "supplementary"


def source_runtime_status(
    source: dict[str, Any],
    queue_row: dict[str, str],
    raw_snapshot: Path | None,
    clean_snapshot: Path | None,
) -> tuple[str, str, str]:
    """Return URL, fetch and cleaner states from persisted local evidence only."""
    queue_status = str(queue_row.get("status", "")).strip().lower()
    if queue_status == "error":
        url_status = "unavailable"
        fetch_status = "failed"
    elif queue_status == "fetched":
        url_status = "active"
        fetch_status = "fetched"
    elif raw_snapshot or clean_snapshot:
        # A historic snapshot exists, but the external URL has not been checked
        # in the current queue yet.
        url_status = "unchecked"
        fetch_status = "fetched"
    else:
        url_status = "unchecked"
        fetch_status = "skipped"
    cleaner_status = "cleaned" if clean_snapshot else ("not_cleaned" if raw_snapshot else "unavailable")
    return url_status, fetch_status, cleaner_status


def source_title(source: dict[str, Any], offer_row: dict[str, str]) -> str:
    return (
        str(source.get("title", "")).strip()
        or str(offer_row.get("title", "")).strip()
        or ("Oficjalne źródło producenta" if source.get("marketplace") == "manufacturer" else "Aukcja Allegro")
    )


def clean_seller_name(value: Any) -> tuple[str, bool]:
    """Ignore UI labels that an upstream parser may have mistaken for a shop."""
    name = str(value or "").strip()
    if normalized(name) in INVALID_SELLER_LABELS:
        return "", bool(name)
    return name, False


def source_seller(source: dict[str, Any]) -> tuple[dict[str, str], bool]:
    path = str(source.get("seller_info_path", "")).strip()
    seller = read_json(PROJECT_ROOT / path, {}) if path else {}
    if not isinstance(seller, dict):
        seller = {}
    seller_name, invalid_name_removed = clean_seller_name(seller.get("seller_name") or source.get("seller_name") or "")
    return {
        "name": seller_name,
        "rating": str(seller.get("seller_rating") or source.get("seller_rating") or "").strip(),
        "reviews_count": str(seller.get("seller_reviews_count") or source.get("seller_reviews_count") or "").strip(),
    }, invalid_name_removed


def listing_records_for(brand: str, model: str) -> dict[str, dict[str, Any]]:
    """Read the existing local targeted-search result, never re-run the search."""
    records: dict[str, dict[str, Any]] = {}
    directory = targeted_dir(brand, model)
    for filename in ("extracted_offers.json", "rejected_offers.json"):
        values = read_json(directory / filename, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            offer_id = str(value.get("offer_id", "")).strip()
            if offer_id:
                records[offer_id] = value
    return records


def source_from_queue(row: dict[str, str], listing: dict[str, Any]) -> dict[str, Any]:
    """Build enough local metadata to show a queued offer before registry attachment."""
    offer_id = str(row.get("offer_id", "")).strip()
    output_dir = str(row.get("output_dir", "")).strip().rstrip("/")
    return {
        "source_id": f"allegro:{offer_id}" if offer_id else "",
        "external_offer_id": offer_id,
        "offer_id": offer_id,
        "marketplace": "allegro",
        "source_type": "marketplace_offer",
        "source_url": str(row.get("normalized_url") or listing.get("canonical_url") or "").strip(),
        "canonical_url": str(row.get("normalized_url") or listing.get("canonical_url") or "").strip(),
        "title": str(listing.get("title", "")).strip(),
        "content_path": f"{output_dir}/technical_clean.md" if output_dir else "",
        "offer_sections_path": f"{output_dir}/offer_sections.json" if output_dir else "",
        "seller_info_path": f"{output_dir}/seller_info.json" if output_dir else "",
        "fetched_at": str(row.get("fetched_at", "")).strip(),
        "quality_score": "",
        "quality_reasons": [],
    }


def normalize_price(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    match = re.search(r"\b(\d{1,3}(?:[ .]\d{3})*|\d+)\s*,\s*(\d{2})\s*(zł|pln)\b", text, re.I)
    if not match:
        return ""
    return f"{match.group(1).replace(' ', '')},{match.group(2)} {match.group(3).lower()}"


def recover_price(
    offer_row: dict[str, str],
    listing: dict[str, Any],
    raw_snapshot: Path | None,
    clean_snapshot: Path | None,
) -> tuple[str, str]:
    """Prefer the listing card, then only persisted raw/clean snapshot text."""
    for value, origin in ((listing.get("price"), "listing"), (offer_row.get("price"), "listing_export")):
        price = normalize_price(value)
        if price:
            return price, origin
    for path, origin in ((raw_snapshot, "raw_snapshot"), (clean_snapshot, "clean_snapshot")):
        if path is None:
            continue
        try:
            price = normalize_price(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            price = ""
        if price:
            return price, origin
    return "", ""


def related_run_dates(group_key: str) -> list[str]:
    """Expose local run history as context without inferring per-offer fetches."""
    dates: list[str] = []
    runs_root = PROJECT_ROOT / "output" / "research_runs"
    if not runs_root.exists():
        return dates
    for path in runs_root.glob("*.json"):
        manifest = read_json(path, {})
        if str(manifest.get("group_key", "")) == group_key:
            date = str(manifest.get("finished_at") or manifest.get("started_at") or "").strip()
            if date:
                dates.append(date)
    return sorted(set(dates))


def build_product_sources_payload(
    product_slug: str,
    group: dict[str, Any],
    state: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    queue_rows: dict[str, dict[str, str]],
    offer_rows: dict[str, dict[str, str]],
    listing_records: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a complete, read-only catalogue from group and selected queue rows."""
    evidence_by_source = source_evidence_index(state)
    contributions_by_source = source_contribution_index(state)
    group_key = str(group.get("group_key", ""))
    related_runs = related_run_dates(group_key)
    brand = str(group.get("brand", ""))
    model = str(group.get("model", ""))
    listing_records = listing_records if listing_records is not None else listing_records_for(brand, model)
    group_sources = {
        str(item.get("source_id", "")).strip(): item
        for item in (group.get("sources", []) if isinstance(group, dict) else [])
        if isinstance(item, dict) and str(item.get("source_id", "")).strip()
    }
    selected_queue = {
        offer_id: row
        for offer_id, row in queue_rows.items()
        if normalized(str(row.get("brand", ""))) == normalized(brand)
        and normalized(str(row.get("detected_model", ""))) == normalized(model)
    }
    source_ids: set[str] = set(group_sources)
    source_ids.update(f"allegro:{offer_id}" for offer_id in selected_queue)

    prepared: list[dict[str, Any]] = []
    for source_id in source_ids:
        group_source = group_sources.get(source_id, {})
        offer_id = str(group_source.get("external_offer_id") or group_source.get("offer_id") or "").strip()
        if not offer_id and source_id.startswith("allegro:"):
            offer_id = source_id.removeprefix("allegro:")
        queue_row = selected_queue.get(offer_id, {})
        listing = listing_records.get(offer_id, {})
        fallback = source_from_queue(queue_row, listing) if queue_row else {}
        source = {**fallback, **group_source, **registry.get(source_id, {})}
        offer_id = str(source.get("external_offer_id") or source.get("offer_id") or offer_id).strip()
        offer_row = offer_rows.get(offer_id, {})
        raw_snapshot, clean_snapshot = local_source_files(source)
        url_status, fetch_status, cleaner_status = source_runtime_status(source, queue_row, raw_snapshot, clean_snapshot)
        evidence_fields = evidence_by_source.get(source_id, [])
        contribution = contributions_by_source.get(source_id, {
            "unique_fields_contributed": [],
            "confirmed_fields": [],
            "conflicting_fields": [],
            "rejected_evidence": [],
            "final_fields_used": [],
        })
        seller, invalid_name_removed = source_seller(source)
        price, price_source = recover_price(offer_row, listing, raw_snapshot, clean_snapshot)
        prepared.append({
            "source_id": source_id,
            "source": source,
            "offer_id": offer_id,
            "queue_row": queue_row,
            "listing": listing,
            "offer_row": offer_row,
            "raw_snapshot": raw_snapshot,
            "clean_snapshot": clean_snapshot,
            "url_status": url_status,
            "fetch_status": fetch_status,
            "cleaner_status": cleaner_status,
            "evidence_fields": evidence_fields,
            "contribution": contribution,
            "seller": seller,
            "invalid_name_removed": invalid_name_removed,
            "price": price,
            "price_source": price_source,
            "attached": source_id in group_sources,
        })

    duplicate_ids: set[str] = set()
    families: dict[str, list[dict[str, Any]]] = {}
    for item in prepared:
        group_family = str(group_sources.get(str(item["source_id"]), {}).get("content_family_id", "")).strip()
        family = str(item["source"].get("content_family_id", "")).strip() or group_family
        if family and item["attached"]:
            families.setdefault(family, []).append(item)
    for family_items in families.values():
        if len(family_items) < 2:
            continue
        # Preserve the source already used in the benchmark when possible.
        preferred = sorted(
            family_items,
            key=lambda item: (not bool(item["evidence_fields"]), str(item["source_id"])),
        )[0]
        duplicate_ids.update(str(item["source_id"]) for item in family_items if item is not preferred)

    records: list[dict[str, Any]] = []
    for item in prepared:
        source = item["source"]
        source_id = str(item["source_id"])
        offer_id = str(item["offer_id"])
        selected = bool(item["queue_row"])
        rejected = selected and item["listing"].get("accepted") is False
        if str(source.get("marketplace", "")).strip() == "manufacturer":
            role = "manufacturer"
        elif rejected:
            role = "rejected"
        elif selected and str(item["queue_row"].get("status", "")).lower() == "error":
            role = "failed"
        elif selected and not item["attached"]:
            role = "fetched_but_unattached"
        elif source_id in duplicate_ids:
            role = "duplicate"
        elif item["evidence_fields"]:
            role = "primary"
        else:
            role = "supplementary"

        original_url = str(source.get("source_url") or source.get("canonical_url") or item["listing"].get("canonical_url") or "").strip()
        canonical_url = str(source.get("canonical_url") or original_url).strip()
        fetched_at = str(source.get("fetched_at") or "").strip()
        queue_fetched_at = str(item["queue_row"].get("fetched_at", "")).strip()
        records.append(
            {
                "source_id": source_id,
                "offer_id": offer_id,
                "title": source_title(source, item["offer_row"]),
                "marketplace": str(source.get("marketplace", "")).strip() or "unknown",
                "source_type": str(source.get("source_type", "")).strip(),
                "role": role,
                "selected": selected,
                "fetched": item["fetch_status"] == "fetched",
                "cleaned": item["cleaner_status"] == "cleaned",
                "attached": bool(item["attached"]),
                "used_in_benchmark": bool(item["contribution"]["final_fields_used"]),
                "original_url": original_url,
                "canonical_url": canonical_url,
                "domain": str(source.get("domain") or urlparse(canonical_url).netloc.lower()).strip(),
                "price": item["price"],
                "price_source": item["price_source"],
                "seller": item["seller"],
                "invalid_seller_removed": bool(item["invalid_name_removed"]),
                "source_status": item["url_status"],
                "fetch_status": item["fetch_status"],
                "cleaner_status": item["cleaner_status"],
                "fetch_error": str(item["queue_row"].get("error_message", "")).strip(),
                "first_fetched_at": fetched_at or queue_fetched_at,
                "last_fetched_at": queue_fetched_at or fetched_at,
                "related_run_dates": related_runs,
                "fields_count": len(item["contribution"]["final_fields_used"]),
                "used_fields": item["contribution"]["final_fields_used"],
                "contribution": item["contribution"],
                "offer_quality": {
                    "score": source.get("quality_score") if source.get("quality_score") not in (None, "") else None,
                    "reasons": source.get("quality_reasons") if isinstance(source.get("quality_reasons"), list) else [],
                },
                "raw_snapshot_path": relative_snapshot_path(item["raw_snapshot"]),
                "clean_snapshot_path": relative_snapshot_path(item["clean_snapshot"]),
                "snapshot_available": bool(item["raw_snapshot"] or item["clean_snapshot"]),
                "content_hash": str(source.get("content_hash", "")).strip(),
            }
        )

    role_order = {
        "primary": 0, "supplementary": 1, "manufacturer": 2, "fetched_but_unattached": 3,
        "duplicate": 4, "failed": 5, "rejected": 6,
    }
    records.sort(key=lambda item: (role_order.get(str(item["role"]), 9), str(item["title"]).lower(), str(item["source_id"])))
    selected_records = [item for item in records if item["selected"]]
    unavailable_count = sum(item["source_status"] == "unavailable" for item in records)
    return {
        "product_slug": product_slug,
        "total": len(records),
        "selected_count": len(selected_records),
        "fetched_count": sum(item["fetched"] for item in selected_records),
        "failed_count": sum(item["role"] == "failed" for item in selected_records),
        "attached_count": sum(item["attached"] for item in selected_records),
        "unattached_count": sum(item["role"] == "fetched_but_unattached" for item in selected_records),
        "duplicate_count": sum(item["role"] == "duplicate" for item in selected_records),
        "rejected_count": sum(item["role"] == "rejected" for item in selected_records),
        "primary_count": sum(item["role"] == "primary" for item in records),
        "supplementary_count": sum(item["role"] == "supplementary" for item in records),
        "manufacturer_count": sum(item["role"] == "manufacturer" for item in records),
        "unavailable_count": unavailable_count,
        "prices_recovered": sum(bool(item["price"]) for item in selected_records),
        "invalid_sellers_removed": sum(bool(item["invalid_seller_removed"]) for item in records),
        "accounted_selected_count": sum(
            item["role"] in {"primary", "supplementary", "fetched_but_unattached", "failed", "duplicate", "rejected"}
            for item in selected_records
        ),
        "sources": records,
    }
def product_sources_payload(product_slug: str) -> dict[str, Any]:
    group_dir = group_dir_for_slug(product_slug)
    group = read_json(group_dir / "group.json", {})
    state = read_json(group_dir / "model_state.json", {})
    registry = {str(item.get("source_id", "")): item for item in read_jsonl(PROJECT_ROOT / "output" / "source_registry.jsonl")}
    return build_product_sources_payload(product_slug, group, state, registry, queue_rows_by_offer_id(), offer_rows_by_offer_id())


def linked_product_sources_payload(product_slug: str) -> dict[str, Any]:
    """Render only explicit ProductSourceLinks; global candidates stay global."""
    sources_by_id = {str(item.get("source_id", "")): item for item in read_source_records()}
    links = [item for item in read_product_source_links() if item.get("product_slug") == product_slug]
    counters = product_source_counters(links, sources_by_id)
    provenance = load_product_provenance(product_slug)
    contribution_index: dict[str, dict[str, list[dict[str, str]]]] = {}
    for field_name, field in (provenance.get("fields", {}) if isinstance(provenance.get("fields"), dict) else {}).items():
        if not isinstance(field, dict):
            continue
        evidence = field.get("evidence_v1", []) if isinstance(field.get("evidence_v1"), list) else []
        aggregate = field.get("aggregate", {}) if isinstance(field.get("aggregate"), dict) else {}
        by_id = {str(item.get("evidence_id", "")): item for item in evidence if isinstance(item, dict)}
        # Every field has one deterministic primary evidence item.  Later
        # independent items are confirmations, not additional new fields.
        buckets = {
            "unique_fields_contributed": [aggregate.get("primary_evidence_id")],
            "confirmed_fields": aggregate.get("confirming_evidence_ids", []),
            "conflicting_fields": aggregate.get("conflicting_evidence_ids", []),
            "rejected_evidence": aggregate.get("rejected_evidence_ids", []),
        }
        for bucket, ids in buckets.items():
            normalized_ids = ids if isinstance(ids, list) else [ids]
            for evidence_id in normalized_ids:
                if not evidence_id:
                    continue
                item = by_id.get(str(evidence_id))
                source_id = str(item.get("source_id", "")) if isinstance(item, dict) else ""
                if not source_id:
                    continue
                entry = {"field_name": str(field_name), "value": str(field.get("value", "X")), "excerpt": str(item.get("excerpt", ""))[:300]}
                contribution_index.setdefault(source_id, {"unique_fields_contributed": [], "confirmed_fields": [], "conflicting_fields": [], "rejected_evidence": [], "final_fields_used": []})[bucket].append(entry)
                if bucket == "unique_fields_contributed":
                    contribution_index[source_id]["final_fields_used"].append(entry)
    records: list[dict[str, Any]] = []
    for link in links:
        source = sources_by_id.get(str(link.get("source_id", "")), {})
        if not source:
            continue
        selection = link.get("selection", {}) if isinstance(link.get("selection"), dict) else {}
        assignment = link.get("assignment", {}) if isinstance(link.get("assignment"), dict) else {}
        usage = link.get("usage", {}) if isinstance(link.get("usage"), dict) else {}
        fetch = source.get("fetch", {}) if isinstance(source.get("fetch"), dict) else {}
        cleaning = source.get("cleaning", {}) if isinstance(source.get("cleaning"), dict) else {}
        content = source.get("content", {}) if isinstance(source.get("content"), dict) else {}
        metadata = source.get("metadata", {}) if isinstance(source.get("metadata"), dict) else {}
        raw_path = PROJECT_ROOT / str(content.get("raw_snapshot_path") or "")
        clean_path = PROJECT_ROOT / str(content.get("clean_snapshot_path") or "")
        raw_snapshot = raw_path if raw_path.exists() else None
        clean_snapshot = clean_path if clean_path.exists() else None
        price, price_source = recover_price({}, {}, raw_snapshot, clean_snapshot)
        seller_name, invalid_seller_removed = clean_seller_name(metadata.get("seller_name"))
        fetch_value = str(fetch.get("status", "not_requested"))
        role_value = str(selection.get("role", "unknown"))
        if fetch_value == "failed":
            role_value = "failed"
        elif fetch_value == "fetched" and assignment.get("status") == "unassigned":
            role_value = "fetched_but_unattached"
        contribution = contribution_index.get(str(source.get("source_id", "")), {"unique_fields_contributed": [], "confirmed_fields": [], "conflicting_fields": [], "rejected_evidence": [], "final_fields_used": []})
        records.append({
            "source_id": source.get("source_id"), "offer_id": source.get("offer_id") or "",
            "title": metadata.get("title") or f"Źródło {source.get('offer_id') or source.get('source_id')}",
            "marketplace": source.get("marketplace") or "unknown", "source_type": source.get("source_type") or "other",
            "role": role_value, "selected": bool(selection.get("selected")), "fetched": fetch_value == "fetched",
            "cleaned": cleaning.get("status") == "cleaned", "attached": assignment.get("status") == "assigned",
            "used_in_benchmark": bool(usage.get("used_in_final_product")),
            "original_url": source.get("original_url") or "", "canonical_url": source.get("canonical_url") or "",
            "domain": source.get("domain") or "", "price": metadata.get("price_amount") or price,
            "price_source": "registry" if metadata.get("price_amount") else price_source,
            "seller": {"name": seller_name, "rating": metadata.get("seller_rating") or "", "reviews_count": ""},
            "invalid_seller_removed": invalid_seller_removed,
            "source_status": "unavailable" if fetch_value in {"failed", "unavailable"} else "active" if fetch_value == "fetched" else "unchecked",
            "fetch_status": fetch_value, "cleaner_status": cleaning.get("status") or "not_started", "fetch_error": fetch.get("error") or "",
            "first_fetched_at": source.get("first_seen_at"), "last_fetched_at": source.get("last_seen_at"),
            "fields_count": int(usage.get("used_fields_count", 0) or 0),
            "offer_quality": {"score": metadata.get("offer_quality_score"), "reasons": []},
            "raw_snapshot_path": content.get("raw_snapshot_path") or "", "clean_snapshot_path": content.get("clean_snapshot_path") or "",
            "snapshot_available": bool(content.get("snapshot_available")), "content_hash": content.get("content_hash") or "",
            "contribution": contribution,
            "lifecycle": {"source": source, "link": link, "usage": usage},
        })
    role_order = {"primary": 0, "supplementary": 1, "manufacturer": 2, "fetched_but_unattached": 3, "duplicate": 4, "failed": 5, "rejected": 6}
    records.sort(key=lambda item: (role_order.get(str(item["role"]), 9), str(item["title"]).casefold(), str(item["source_id"])))
    return {
        "product_slug": product_slug, "total": len(records), "sources": records, **counters,
        "failed_count": counters["fetch_failed_count"], "attached_count": counters["assigned_count"],
        "primary_count": sum(item["role"] == "primary" for item in records),
        "supplementary_count": sum(item["role"] == "supplementary" for item in records),
        "manufacturer_count": sum(item["role"] == "manufacturer" for item in records),
    }


def source_assessment(group: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    registry = {str(item.get("source_id", "")): item for item in read_jsonl(PROJECT_ROOT / "output" / "source_registry.jsonl")}
    assessed: list[dict[str, Any]] = []
    new_sources: list[str] = []
    changed_sources: list[str] = []
    unavailable_sources: list[str] = []
    for item in group.get("sources", []):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id", "")).strip()
        source = {**item, **registry.get(source_id, {})}
        raw, clean = local_source_files(source)
        current_hash = hash_file(clean or raw) if (clean or raw) else ""
        stored_hash = str(source.get("content_hash", "")).strip()
        status = "active" if (raw or clean) else "unavailable"
        assessed.append({"source_id": source_id, "source_status": status, "content_hash": current_hash})
        if not source_id or source_id not in registry:
            new_sources.append(source_id or "unknown")
        if stored_hash and current_hash and stored_hash != current_hash:
            changed_sources.append(source_id)
        if status == "unavailable":
            unavailable_sources.append(source_id)
    return assessed, new_sources, changed_sources, unavailable_sources


def copied_history_snapshot(group_dir: Path, run_id: str, mode: str, coverage_before: float | None) -> tuple[Path, dict[str, Any]]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    history_dir = group_dir / "history" / timestamp
    history_dir.mkdir(parents=True, exist_ok=False)
    for filename in ("model_state.json", "group.json"):
        source = group_dir / filename
        if source.exists():
            shutil.copy2(source, history_dir / filename)
    manifest = {
        "run_id": run_id,
        "mode": mode,
        "started_at": utc_now(),
        "finished_at": None,
        "sources_before": 0,
        "sources_after": 0,
        "new_sources": [],
        "changed_sources": [],
        "unavailable_sources": [],
        "fields_changed": [],
        "coverage_before": coverage_before,
        "coverage_after": None,
    }
    atomic_write(history_dir / "refresh_manifest.json", manifest)
    return history_dir, manifest


def state_fields(path: Path) -> dict[str, Any]:
    state = read_json(path, {})
    return state.get("fields", {}) if isinstance(state.get("fields"), dict) else {}


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    names = set(before) | set(after)
    return sorted(
        name for name in names
        if json.dumps(before.get(name, {}), ensure_ascii=False, sort_keys=True) != json.dumps(after.get(name, {}), ensure_ascii=False, sort_keys=True)
    )


def analysis_status_payload(product_slug: str) -> dict[str, Any]:
    """Describe whether a model can be analysed from data already on disk."""
    group_dir = group_dir_for_slug(product_slug)
    group = read_json(group_dir / "group.json", {})
    state = read_json(group_dir / "model_state.json", {})
    sources = [item for item in group.get("sources", []) if isinstance(item, dict)]
    state_fields_value = state.get("fields", {}) if isinstance(state.get("fields"), dict) else {}
    processed = {str(value) for value in state.get("processed_source_ids", []) if str(value)}
    source_ids = {str(item.get("source_id", "")) for item in sources if str(item.get("source_id", ""))}
    unprocessed = sorted(source_ids - processed)
    uncleaned: list[str] = []
    usable_source_ids: list[str] = []
    for source in sources:
        source_id = str(source.get("source_id", "")).strip()
        raw, clean = local_source_files(source)
        if raw or clean:
            usable_source_ids.append(source_id)
        if raw and not clean and str(source.get("external_offer_id") or source.get("offer_id") or "").strip():
            uncleaned.append(str(source.get("external_offer_id") or source.get("offer_id")))
    open_fields = sum(
        isinstance(item, dict) and (str(item.get("value", "X") or "X") == "X" or item.get("status") in {"open", "unclear", "conflicting"})
        for item in state_fields_value.values()
    )
    states = load_product_states()
    canonical = {**default_product_state(product_slug), **states.get(product_slug, {})}
    if has_valid_final_result(str(group.get("group_key", "")), state_fields_value):
        canonical["result_status"] = "ready"
    status = public_product_status(canonical)
    return {
        "product_slug": product_slug,
        "group_key": str(group.get("group_key", "")),
        "status": status,
        "sources_total": len(sources),
        "sources_with_snapshot": len(usable_source_ids),
        "unprocessed_source_ids": unprocessed,
        "uncleaned_offer_ids": sorted(set(uncleaned)),
        "open_fields": open_fields,
        "can_analyze_saved_data": bool(usable_source_ids),
        "uses_network_by_default": False,
        "canonical_state": canonical,
    }


def runtime_benchmark_products(benchmark_group: str) -> list[dict[str, Any]]:
    """Project persisted legacy model groups into the Unit 8 scorer input."""
    values: list[dict[str, Any]] = []
    for path in sorted((PROJECT_ROOT / "output" / "model_groups").glob("*/group.json")):
        group = read_json(path, {})
        if not isinstance(group, dict) or str(group.get("benchmark_group", "")).strip() != str(benchmark_group).strip():
            continue
        state = read_json(path.parent / "model_state.json", {})
        state = state if isinstance(state, dict) else {}
        fields = state.get("fields", {}) if isinstance(state.get("fields"), dict) else {}
        product = next((item for item in load_products() if str(item.get("group_key", "")).strip() == str(group.get("group_key", "")).strip()), {})
        values.append({
            "product_id": str(group.get("product_id") or product.get("product_id") or group.get("group_key") or path.parent.name),
            "brand": str(group.get("brand") or state.get("brand") or product.get("brand") or ""),
            "model": str(group.get("model") or state.get("model") or product.get("model") or ""),
            "configuration": group.get("configuration", state.get("configuration", product.get("configuration", ""))),
            "group_key": str(group.get("group_key") or product.get("group_key") or "").strip(),
            "benchmark_group": str(group.get("benchmark_group", benchmark_group)).strip(),
            "attributes": fields,
        })
    return values


def runtime_semantic_benchmark(product_slug: str, benchmark_group: str) -> tuple[dict[str, Any], dict[str, Any]]:
    products = runtime_benchmark_products(benchmark_group)
    anchor = next((item for item in products if product_slug_for(item.get("brand", ""), item.get("model", ""), item.get("configuration", "")) == product_slug), None)
    if anchor is None:
        return {"status": "insufficient_data", "reason": "no_scored_runtime_products", "participants": []}, {"status": "no_data", "median": None, "min": None, "max": None, "seller_count": 0, "observations": []}
    candidates = [item for item in products if item is not anchor]
    if normalized_benchmark_brand(anchor.get("brand")) == "lionelo":
        benchmark = build_internal_benchmark(products, benchmark_group)
    else:
        benchmark = build_competitive_benchmark(anchor, candidates)
    observations: list[dict[str, Any]] = []
    for item in products:
        if item is not anchor and normalized_benchmark_configuration(item.get("configuration")) != normalized_benchmark_configuration(anchor.get("configuration")):
            continue
        source_group = next((path.parent for path in (PROJECT_ROOT / "output" / "model_groups").glob("*/group.json") if str(read_json(path, {}).get("group_key", "")) == str(item.get("group_key", ""))), None)
        if source_group:
            group = read_json(source_group / "group.json", {})
            for offer in group.get("sources", group.get("offers", [])) if isinstance(group, dict) else []:
                if not isinstance(offer, dict):
                    continue
                if offer.get("price") is not None:
                    observations.append({"seller_id": offer.get("seller_id") or offer.get("seller") or offer.get("domain"), "price": offer.get("price"), "observed_at": offer.get("observed_at") or offer.get("fetched_at"), "source_id": offer.get("source_id")})
    return benchmark, aggregate_prices(observations)


def benchmark_payload(product_slug: str) -> dict[str, Any]:
    """Return a category-level matrix, never a copy of a single product card."""
    group_dir = group_dir_for_slug(product_slug)
    current_group = read_json(group_dir / "group.json", {})
    catalog_product = product_for_group_key(str(current_group.get("group_key", "")))
    category_record = {**current_group, **catalog_product}
    category_key = str(category_record.get("category_key", "")).strip()
    benchmark_group = str(category_record.get("benchmark_group", "")).strip()
    category = str(category_record.get("benchmark_category", "")).strip()
    taxonomy_version = str(current_group.get("taxonomy_version", "")).strip()
    try:
        validate_category_assignment(category_key, benchmark_group)
        taxonomy_ready = True
    except CategoryValidationError:
        taxonomy_ready = False
    current_group_key = str(current_group.get("group_key", ""))
    models: list[dict[str, Any]] = []
    fields_order: list[str] = []
    seen_groups: set[str] = set()
    for path in sorted((PROJECT_ROOT / "output" / "model_groups").glob("*/group.json")):
        group = read_json(path, {})
        group_key = str(group.get("group_key", "")).strip()
        if (
            not taxonomy_ready
            or not group_key
            or group_key in seen_groups
            or not same_benchmark_group(category_record, {**group, **product_for_group_key(group_key)})
        ):
            continue
        seen_groups.add(group_key)
        state = read_json(path.parent / "model_state.json", {})
        fields = state.get("fields", {}) if isinstance(state.get("fields"), dict) else {}
        if not fields:
            continue
        slug = path.parent.name
        values: dict[str, dict[str, str]] = {}
        for field_name, item in fields.items():
            if not isinstance(item, dict):
                continue
            if field_name not in fields_order:
                fields_order.append(field_name)
            values[str(field_name)] = {
                "value": str(item.get("value", "X") or "X"),
                "status": str(item.get("status", "open") or "open"),
                "confidence": str(item.get("confidence", "low") or "low"),
            }
        models.append({
            "slug": slug,
            "group_key": group_key,
            "brand": str(group.get("brand", "")),
            "model": str(group.get("model", "")),
            "coverage": coverage_for_group(group_key),
            "values": values,
        })
    models.sort(key=lambda item: (item["slug"] != product_slug, str(item["brand"]).lower(), str(item["model"]).lower()))
    semantic_benchmark, price_summary = runtime_semantic_benchmark(product_slug, benchmark_group)
    return {
        "product_slug": product_slug,
        "benchmark_category": category,
        "category_key": category_key,
        "benchmark_group": benchmark_group,
        "taxonomy_version": taxonomy_version,
        "taxonomy_status": "classified" if taxonomy_ready else "review_required",
        "current_group_key": current_group_key,
        "models": models,
        "fields": fields_order,
        "has_comparison": len(models) > 1,
        "semantic_benchmark": semantic_benchmark,
        "price_summary": price_summary,
    }


def write_local_analysis_context(offer_ids: list[str]) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", prefix="fieldnote-analysis-", encoding="utf-8", delete=False)
    with handle:
        json.dump({"fetched_offer_ids": offer_ids}, handle, ensure_ascii=False)
    return Path(handle.name)


def analysis_worker(run_id: str, product_slug: str, refresh_sources: bool) -> None:
    """Analyse persisted snapshots; network work is opt-in through refresh_sources."""
    payload = read_run(run_id)
    group_dir = group_dir_for_slug(product_slug)
    group = read_json(group_dir / "group.json", {})
    group_key = str(group.get("group_key", ""))
    before_fields = state_fields(group_dir / "model_state.json")
    coverage_before = coverage_for_group(group_key)
    history_dir, manifest = copied_history_snapshot(group_dir, run_id, "analysis", coverage_before)
    context_path: Path | None = None
    try:
        payload.update({"status": "running", "current_step": "Przygotowanie zapisanych źródeł", "progress": 4})
        set_product_analysis_status(product_slug, "analysis_running", run_id=run_id)
        payload["analysis"] = {"refresh_sources": refresh_sources, "used_sources": [], "coverage_before": coverage_before}
        save_run(payload)
        source_pipeline_status = "success"

        if refresh_sources:
            # This is explicitly opt-in. It reuses the existing production runner
            # instead of duplicating targeted-search or fetch logic here.
            command = [
                sys.executable, str(SCRIPTS_ROOT / "run_model_research_pipeline.py"),
                "--marketplace", "allegro", "--brand", str(group.get("brand", "")),
                "--model", str(group.get("model", "")), "--apply", "--resume", "--skip-product-profile",
            ]
            result = logged_command(payload, "Odświeżanie źródeł i analiza", 45, command)
            source_pipeline_status = pipeline_status_from_result(result)
            if source_pipeline_status == "failed":
                raise RuntimeError("Odświeżanie źródeł i analiza zakończyły się błędem.")
            if source_pipeline_status == "partial":
                payload["analysis_warning"] = SOURCE_ANALYSIS_TIMEOUT_MESSAGE if controlled_analysis_timeout(result) else "Analiza źródeł zakończyła się częściowo. Zachowano dotychczasowe dane."
                update_run_log(payload, payload["analysis_warning"])
        else:
            status = analysis_status_payload(product_slug)
            if not status["can_analyze_saved_data"]:
                raise RuntimeError("Brak lokalnych snapshotów do analizy tego produktu.")
            source_offer_ids = [
                str(item.get("external_offer_id") or item.get("offer_id") or "").strip()
                for item in group.get("sources", []) if isinstance(item, dict)
            ]
            source_offer_ids = [item for item in source_offer_ids if item]
            context_path = write_local_analysis_context(source_offer_ids)
            payload["analysis"]["used_sources"] = source_offer_ids
            save_run(payload)
            if status["uncleaned_offer_ids"]:
                cleaner_command = [sys.executable, str(SCRIPTS_ROOT / "clean_offer_pages_technical.py")]
                for offer_id in status["uncleaned_offer_ids"]:
                    cleaner_command.extend(["--offer-id", str(offer_id)])
                cleaned = logged_command(payload, "Oczyszczanie nieoczyszczonych źródeł", 18, [
                    *cleaner_command,
                ])
                if cleaned.returncode != 0:
                    raise RuntimeError("Nie udało się oczyścić zapisanych źródeł.")
            else:
                update_run_log(payload, "Wszystkie lokalne źródła są już oczyszczone.")

            registry = logged_command(payload, "Aktualizacja rejestru źródeł", 34, [
                sys.executable, str(SCRIPTS_ROOT / "build_source_registry.py"), "--offer-ids-file", str(context_path),
            ])
            if registry.returncode != 0:
                raise RuntimeError("Nie udało się zaktualizować rejestru źródeł.")
            grouping = logged_command(payload, "Grupowanie produktu", 48, [
                sys.executable, str(SCRIPTS_ROOT / "build_model_groups.py"), "--group-key", group_key,
                "--max-offers-per-model", "5", "--force",
            ])
            if grouping.returncode != 0:
                raise RuntimeError("Nie udało się zaktualizować grupy produktu.")
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("Brak OPENAI_API_KEY. Możesz przeglądać dane; analiza AI wymaga lokalnej konfiguracji klucza.")
            cascade = logged_command(payload, "Analiza AI zapisanych źródeł", 72, [
                sys.executable, str(SCRIPTS_ROOT / "extract_model_facts_cascade.py"), "--group-key", group_key, "--resume",
            ])
            if controlled_analysis_timeout(cascade):
                source_pipeline_status = "partial"
                payload["analysis_warning"] = SOURCE_ANALYSIS_TIMEOUT_MESSAGE
                update_run_log(payload, payload["analysis_warning"])
            elif cascade.returncode != 0:
                raise RuntimeError("Analiza AI zapisanych źródeł zakończyła się błędem.")

        if not refresh_sources:
            benchmark = logged_command(payload, "Aktualizacja benchmarku", 84, [sys.executable, str(SCRIPTS_ROOT / "build_model_benchmark.py")])
            if benchmark.returncode != 0:
                raise RuntimeError("Nie udało się zaktualizować benchmarku.")
            coverage = logged_command(payload, "Aktualizacja coverage", 91, [sys.executable, str(SCRIPTS_ROOT / "report_model_coverage.py")])
            if coverage.returncode != 0:
                raise RuntimeError("Nie udało się przeliczyć coverage.")
        terminal_status = finalize_source_run(payload, run_id, source_pipeline_status)

        after_fields = state_fields(group_dir / "model_state.json")
        changed = changed_fields(before_fields, after_fields)
        coverage_after = coverage_for_group(group_key)
        state_after_path = group_dir / "model_state.json"
        if state_after_path.exists():
            shutil.copy2(state_after_path, history_dir / "result_model_state.json")
        manifest.update({"finished_at": utc_now(), "sources_after": len(group.get("sources", [])), "fields_changed": changed, "coverage_after": coverage_after})
        atomic_write(history_dir / "refresh_manifest.json", manifest)
        payload["analysis"].update({"fields_changed": len(changed), "coverage_after": coverage_after})
        payload.update({"status": "succeeded" if terminal_status == "success" else "partial", "pipeline_status": terminal_status, "current_step": "Analiza zakończona" if terminal_status == "success" else "Analiza zakończona częściowo", "progress": 100, "finished_at": utc_now()})
        set_product_analysis_status(product_slug, "ready" if terminal_status == "success" else "refresh_recommended", run_id=run_id)
        save_run(payload)
    except RunCancelledError as exc:
        manifest["finished_at"] = utc_now()
        atomic_write(history_dir / "refresh_manifest.json", manifest)
        payload.update({
            "status": "cancelled",
            "current_step": "Analiza anulowana",
            "error": str(exc),
            "finished_at": utc_now(),
        })
        set_product_analysis_status(product_slug, "cancelled", error=str(exc), run_id=run_id)
        save_run(payload)
    except Exception as exc:
        manifest["finished_at"] = utc_now()
        atomic_write(history_dir / "refresh_manifest.json", manifest)
        payload.update({"status": "failed", "current_step": "Analiza zatrzymała się", "error": str(exc), "finished_at": utc_now()})
        set_product_analysis_status(product_slug, "analysis_failed", error=str(exc), run_id=run_id)
        save_run(payload)
    finally:
        if context_path:
            context_path.unlink(missing_ok=True)
        RUN_COORDINATOR.release_product(run_id)


def logged_command(payload: dict[str, Any], step: str, progress: int, command: list[str]) -> subprocess.CompletedProcess[str]:
    payload["current_step"] = step
    payload["progress"] = progress
    heartbeat_run(payload)
    run_id = str(payload.get("run_id", ""))
    work_directory = RUN_COORDINATOR.work_directory(run_id)
    work_directory.mkdir(parents=True, exist_ok=True)
    stdout_path = work_directory / "child_stdout.log"
    stderr_path = work_directory / "child_stderr.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=pipeline_environment(),
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
        payload["child_pid"] = process.pid
        heartbeat_run(payload)
        deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
        while process.poll() is None:
            if time.monotonic() >= deadline:
                terminate_process_group(process)
                process.wait(timeout=10)
                raise RuntimeError(f"Etap '{step}' przekroczył limit {RUN_TIMEOUT_SECONDS}s.")
            latest = read_run(run_id)
            if latest.get("cancel_requested_at"):
                terminate_process_group(process)
                process.wait(timeout=10)
                raise RunCancelledError("Run został anulowany przez użytkownika.")
            time.sleep(0.25)
            heartbeat_run(payload)
    except BaseException:
        if process is not None and process.poll() is None:
            terminate_process_group(process)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        raise
    finally:
        payload["child_pid"] = None
        stdout_handle.close()
        stderr_handle.close()
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    result = subprocess.CompletedProcess(command, process.returncode if process is not None else 1, stdout, stderr)
    for line in (result.stdout + result.stderr).splitlines():
        update_run_log(payload, f"{step}: {line}")
    heartbeat_run(payload)
    return result


def controlled_analysis_timeout(result: subprocess.CompletedProcess[str]) -> bool:
    """Recognize the cascade's documented safe timeout outcome, not a traceback."""
    output = f"{result.stdout}\n{result.stderr}"
    return (
        result.returncode == CONTROLLED_SOURCE_ANALYSIS_EXIT
        and "source_analysis_status=failed" in output
        and "source_analysis_error_code=source_analysis_timeout" in output
    )


def pipeline_status_from_result(result: subprocess.CompletedProcess[str]) -> str:
    """Read the canonical runner status while preserving the controlled timeout."""
    output = f"{result.stdout}\n{result.stderr}"
    matches = re.findall(r"^pipeline_status=([a-z]+)$", output, flags=re.MULTILINE)
    status = matches[-1] if matches else ""
    if controlled_analysis_timeout(result):
        return "partial"
    if status in {"success", "partial", "failed"}:
        return status
    return "failed" if result.returncode else "success"


def profile_status_allows_success(status: str) -> bool:
    return status in {"generated", "cached"}


def final_run_status(source_status: str, profile_status: str) -> str:
    """A source success is not a full success when the profile is unavailable."""
    if source_status not in {"success", "partial"}:
        return "failed"
    if source_status == "partial" or not profile_status_allows_success(profile_status):
        return "partial"
    return "success"


def export_snapshot_for_owned_run(payload: dict[str, Any], run_id: str, progress: int = 97) -> bool:
    """The API parent owns exactly one frontend export after the source pipeline."""
    try:
        with global_aggregation_lock(PROJECT_ROOT / "output" / "run_locks", run_id):
            snapshot = logged_command(
                payload,
                "Eksport danych do FIELDNOTE",
                progress,
                [sys.executable, str(SCRIPTS_ROOT / "export_frontend_snapshot.py")],
            )
    except LockUnavailableError:
        payload["snapshot_updated"] = False
        payload["snapshot_warning"] = "Inny run aktualizuje katalog frontendowy."
        return False
    payload["snapshot_updated"] = snapshot.returncode == 0
    if snapshot.returncode != 0:
        payload["snapshot_warning"] = "Research zakończony, ale nie udało się odświeżyć katalogu frontendowego."
    return bool(payload["snapshot_updated"])


def finalize_source_run(payload: dict[str, Any], run_id: str, source_status: str) -> str:
    """Run the parent-owned post-processing exactly once after source work."""
    profile_status = generate_profile_for_owned_run(payload, run_id)
    status = final_run_status(source_status, profile_status)
    # The generated frontend snapshot reads product_state.json. Persist the
    # terminal state before exporting so a completed partial run cannot leave
    # the UI showing the earlier "analysis_running" state.
    set_product_analysis_status(
        str(payload.get("product_slug", "")),
        "ready" if status == "success" else "refresh_recommended",
        run_id=run_id,
    )
    snapshot_updated = export_snapshot_for_owned_run(payload, run_id, 97)
    if not snapshot_updated and status == "success":
        payload["snapshot_warning"] = payload.get("snapshot_warning") or "Nie udało się wyeksportować aktualnych danych do widoku produktu."
        set_product_analysis_status(str(payload.get("product_slug", "")), "refresh_recommended", run_id=run_id)
        return "partial"
    return status


def refresh_worker(run_id: str, product_slug: str, mode: str) -> None:
    payload = read_run(run_id)
    payload.update({"status": "running", "current_step": "Przygotowanie wersji historycznej", "progress": 2})
    set_product_analysis_status(product_slug, "analysis_running", run_id=run_id)
    save_run(payload)
    group_dir = group_dir_for_slug(product_slug)
    group = read_json(group_dir / "group.json", {})
    group_key = str(group.get("group_key", ""))
    before_fields = state_fields(group_dir / "model_state.json")
    coverage_before = coverage_for_group(group_key)
    history_dir, manifest = copied_history_snapshot(group_dir, run_id, mode, coverage_before)
    try:
        assessed, new_sources, changed_sources, unavailable_sources = source_assessment(group)
        manifest["sources_before"] = len(assessed)
        manifest["new_sources"] = new_sources
        manifest["changed_sources"] = changed_sources
        manifest["unavailable_sources"] = unavailable_sources
        payload["refresh"] = {
            "mode": mode,
            "history_path": str(history_dir.relative_to(PROJECT_ROOT)),
            "new_sources": len(new_sources),
            "changed_sources": len(changed_sources),
            "unavailable_sources": len(unavailable_sources),
            "fields_changed": 0,
            "coverage_before": coverage_before,
            "coverage_after": coverage_before,
            "source_statuses": assessed,
        }
        atomic_write(history_dir / "refresh_manifest.json", manifest)
        save_run(payload)

        source_pipeline_status = "success"
        if mode == "incremental":
            # The canonical runner owns search, merge, fetch, clean, registry,
            # grouping, analysis, benchmark and coverage exactly once.
            result = logged_command(payload, "Odświeżanie źródeł i analiza", 72, [
                sys.executable, str(SCRIPTS_ROOT / "run_model_research_pipeline.py"),
                "--marketplace", "allegro", "--brand", str(group.get("brand", "")),
                "--model", str(group.get("model", "")), "--apply", "--resume", "--skip-product-profile",
            ])
            source_pipeline_status = pipeline_status_from_result(result)
            if source_pipeline_status == "failed":
                raise RuntimeError("Odświeżanie źródeł i analiza zakończyły się błędem.")
            if source_pipeline_status == "partial":
                payload["analysis_warning"] = SOURCE_ANALYSIS_TIMEOUT_MESSAGE if controlled_analysis_timeout(result) else "Analiza źródeł zakończyła się częściowo. Zachowano dotychczasowe dane."
                update_run_log(payload, payload["analysis_warning"])
        else:
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("Pełna ponowna analiza wymaga OPENAI_API_KEY; lokalne snapshoty nie zostały zmienione.")
            result = logged_command(payload, "Pełna ponowna analiza lokalnych snapshotów", 55, [
                sys.executable, str(SCRIPTS_ROOT / "extract_model_facts_cascade.py"), "--group-key", group_key, "--reset-state",
            ])
            if controlled_analysis_timeout(result):
                source_pipeline_status = "partial"
                payload["analysis_warning"] = SOURCE_ANALYSIS_TIMEOUT_MESSAGE
                update_run_log(payload, payload["analysis_warning"])
            elif result.returncode != 0:
                raise RuntimeError("Pełna ponowna analiza zakończyła się błędem.")
            benchmark = logged_command(payload, "Aktualizacja benchmarku", 76, [sys.executable, str(SCRIPTS_ROOT / "build_model_benchmark.py")])
            if benchmark.returncode != 0:
                raise RuntimeError("Nie udało się zaktualizować benchmarku.")
            coverage = logged_command(payload, "Aktualizacja coverage", 84, [sys.executable, str(SCRIPTS_ROOT / "report_model_coverage.py")])
            if coverage.returncode != 0:
                raise RuntimeError("Nie udało się przeliczyć coverage.")

        terminal_status = finalize_source_run(payload, run_id, source_pipeline_status)

        refreshed_group = read_json(group_dir / "group.json", {})
        after_fields = state_fields(group_dir / "model_state.json")
        changed = changed_fields(before_fields, after_fields)
        coverage_after = coverage_for_group(group_key)
        state_after_path = group_dir / "model_state.json"
        if state_after_path.exists():
            shutil.copy2(state_after_path, history_dir / "result_model_state.json")
        manifest.update({
            "finished_at": utc_now(),
            "sources_after": len(refreshed_group.get("sources", [])),
            "fields_changed": changed,
            "coverage_after": coverage_after,
        })
        atomic_write(history_dir / "refresh_manifest.json", manifest)
        payload["refresh"].update({"fields_changed": len(changed), "coverage_after": coverage_after})
        payload.update({"status": "succeeded" if terminal_status == "success" else "partial", "pipeline_status": terminal_status, "current_step": "Odświeżono dane" if terminal_status == "success" else "Odświeżono dane częściowo", "progress": 100, "finished_at": utc_now()})
        set_product_analysis_status(product_slug, "ready" if terminal_status == "success" else "refresh_recommended", run_id=run_id)
        save_run(payload)
    except RunCancelledError as exc:
        manifest["finished_at"] = utc_now()
        atomic_write(history_dir / "refresh_manifest.json", manifest)
        payload.update({
            "status": "cancelled",
            "current_step": "Odświeżanie anulowane",
            "error": str(exc),
            "finished_at": utc_now(),
        })
        set_product_analysis_status(product_slug, "cancelled", error=str(exc), run_id=run_id)
        save_run(payload)
    except Exception as exc:
        manifest["finished_at"] = utc_now()
        atomic_write(history_dir / "refresh_manifest.json", manifest)
        payload.update({"status": "failed", "current_step": "Odświeżanie zatrzymało się", "error": str(exc), "finished_at": utc_now()})
        set_product_analysis_status(product_slug, "analysis_failed", error=str(exc), run_id=run_id)
        save_run(payload)
    finally:
        RUN_COORDINATOR.release_product(run_id)


def update_run_log(payload: dict[str, Any], line: str) -> None:
    line = redact(line.rstrip())
    if not line:
        return
    logs = payload.setdefault("logs", [])
    if not isinstance(logs, list):
        logs = []
        payload["logs"] = logs
    logs.append(line)
    if len(logs) > MAX_LOG_LINES:
        del logs[:-MAX_LOG_LINES]
    combined = "\n".join(str(item) for item in logs)
    if len(combined) > MAX_LOG_CHARS:
        payload["logs"] = combined[-MAX_LOG_CHARS:].splitlines()


def update_progress_from_line(payload: dict[str, Any], line: str) -> None:
    match = re.match(r"\[(\d+)/9\]\s+(.+)", line)
    if match:
        current = int(match.group(1))
        payload["current_step"] = match.group(2).split("(", 1)[0].strip()
        payload["progress"] = max(payload.get("progress", 0), min(95, round((current - 1) / 9 * 100)))


def heartbeat_run(payload: dict[str, Any]) -> None:
    payload["last_heartbeat_at"] = utc_now()
    payload["lease_expires_at"] = lease_until(LEASE_SECONDS)
    save_run(payload)


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    """Stop only the process tree created for this local run."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (AttributeError, ProcessLookupError, PermissionError):
        process.terminate()


def commit_cached_manufacturer_source(payload: dict[str, Any]) -> bool:
    """Run the shared manufacturer lifecycle from an already saved snapshot.

    This deliberately never enables network or OpenAI. A missing official
    source is an optional-source warning, not a reason to discard a successful
    marketplace research run.
    """
    selected = payload.get("selected_manufacturer_source_ids", [])
    if not payload.get("include_manufacturer_sources") or not isinstance(selected, list) or not selected:
        return True
    command = [
        sys.executable, str(SCRIPTS_ROOT / "check_manufacturer_pipeline_live.py"),
        "--brand", str(payload.get("brand", "")), "--model", str(payload.get("model", "")),
        "--max-sources", "1", "--resume", "--no-fetch", "--no-openai",
    ]
    payload["current_step"] = "Zapisywanie źródła producenta"
    payload["progress"] = max(int(payload.get("progress", 0)), 93)
    heartbeat_run(payload)
    result = run_command(command)
    output = f"{result.stdout}\n{result.stderr}".strip()
    for line in output.splitlines():
        update_run_log(payload, f"manufacturer: {line}")
    if result.returncode != 0 or "terminal_status=success" not in output:
        payload["manufacturer_warning"] = "Nie udało się zapisać wybranego źródła producenta z lokalnego cache."
        return False
    source_id_match = re.findall(r"^source_id=(.+)$", output, flags=re.MULTILINE)
    source_id = source_id_match[-1].strip() if source_id_match else ""
    if source_id and source_id not in {str(item) for item in selected}:
        payload["manufacturer_warning"] = "Kontrolowany runner zwrócił inne źródło producenta niż wybrane w Research."
        return False
    payload["manufacturer_lifecycle_committed"] = True
    return True


def generate_profile_for_owned_run(payload: dict[str, Any], run_id: str) -> str:
    """Generate once after source commit and return an explicit terminal status."""
    if os.getenv("PRODUCT_PROFILE_AI_ENABLED", "").lower() not in {"1", "true", "yes"}:
        cached = get_profile(str(payload["product_slug"]))
        if str(cached.get("profile_status", "")) == "generated":
            payload.update({"product_profile_stage": "completed", "product_profile_status": "cached", "product_profile_warning": ""})
            return "cached"
        payload.update({
            "product_profile_stage": "skipped",
            "product_profile_status": "skipped",
            "product_profile_warning": "Generowanie profilu AI jest wyłączone w lokalnej konfiguracji.",
        })
        return "skipped"
    try:
        payload.update({"current_step": "Generowanie profilu produktu", "progress": max(int(payload.get("progress", 0)), 96)})
        heartbeat_run(payload)
        profile, cached = generate_or_load_profile(str(payload["product_slug"]), allow_openai=True, owned_lock_run_id=run_id)
        profile_status = str(profile.get("profile_status", "failed"))
        generation = profile.get("generation", {}) if isinstance(profile.get("generation"), dict) else {}
        if profile_status == "generated":
            status = "cached" if cached else "generated"
            payload.update({"product_profile_stage": "completed", "product_profile_status": status, "product_profile_warning": ""})
            return status
        if profile_status == "not_generated":
            warning = str(generation.get("failure_reason", "Brak wystarczających danych źródłowych do wygenerowania profilu."))
            status = "insufficient_profile_evidence" if str(generation.get("failure_code", "")) == "insufficient_profile_evidence" else "skipped"
            payload.update({"product_profile_stage": "partial", "product_profile_status": status, "product_profile_warning": warning})
            update_run_log(payload, f"profile: {status}: {warning}")
            return status
        warning = str(generation.get("failure_reason", "Profil nie został wygenerowany."))
        payload.update({"product_profile_stage": "failed", "product_profile_status": "failed", "product_profile_warning": warning})
        update_run_log(payload, f"profile: failed: {warning}")
        return "failed"
    except Exception as exc:
        warning = "Nie udało się wygenerować profilu produktu. Zachowano dotychczasowe dane."
        payload.update({"product_profile_stage": "failed", "product_profile_status": "failed", "product_profile_warning": warning})
        update_run_log(payload, f"profile: failed: {warning}")
        return "failed"


def pipeline_worker(run_id: str, command: list[str]) -> None:
    payload = read_run(run_id)
    payload["status"] = "running"
    payload["current_step"] = "Przygotowanie pipeline’u"
    payload["progress"] = 1
    set_product_analysis_status(str(payload.get("product_slug", "")), "analysis_running", run_id=run_id)
    heartbeat_run(payload)
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=pipeline_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
        assert process.stdout is not None
        payload["child_pid"] = process.pid
        heartbeat_run(payload)
        lines: Queue[str | None] = Queue()

        def collect_output() -> None:
            assert process is not None and process.stdout is not None
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=collect_output, daemon=True, name=f"fieldnote-output-{run_id}").start()
        started = time.monotonic()
        stream_closed = False
        cancelled = False
        timed_out = False
        while not stream_closed or process.poll() is None:
            try:
                line = lines.get(timeout=1.0)
                if line is None:
                    stream_closed = True
                else:
                    update_run_log(payload, line)
                    update_progress_from_line(payload, line)
            except Empty:
                pass
            latest = read_run(run_id)
            if latest.get("cancel_requested_at"):
                cancelled = True
                terminate_process_group(process)
            if time.monotonic() - started > RUN_TIMEOUT_SECONDS:
                timed_out = True
                terminate_process_group(process)
            heartbeat_run(payload)
            if (cancelled or timed_out) and process.poll() is not None:
                break
        returncode = process.wait(timeout=15)
        output = "\n".join(str(line) for line in payload.get("logs", []))
        result = re.findall(r"^pipeline_status=([a-z]+)$", output, flags=re.MULTILINE)
        pipeline_status = result[-1] if result else "failed"
        if returncode != 0 and pipeline_status not in {"partial"}:
            pipeline_status = "failed"
        if cancelled:
            payload.update({"status": "cancelled", "pipeline_status": pipeline_status, "current_step": "Proces anulowany", "error": "Run został anulowany przez użytkownika."})
            return
        if timed_out:
            payload.update({"status": "timed_out", "pipeline_status": pipeline_status, "current_step": "Przekroczono limit czasu", "error": f"Pipeline przekroczył limit {RUN_TIMEOUT_SECONDS}s."})
            return
        if pipeline_status == "preview":
            pipeline_status = "success"
        if pipeline_status not in {"success", "partial", "failed"}:
            pipeline_status = "failed"
        if pipeline_status in {"success", "partial"}:
            if not commit_cached_manufacturer_source(payload):
                pipeline_status = "partial"
            pipeline_status = finalize_source_run(payload, run_id, pipeline_status)
        payload["pipeline_status"] = pipeline_status
        payload["status"] = "succeeded" if pipeline_status == "success" else "partial" if pipeline_status == "partial" else "failed"
        payload["progress"] = 100 if pipeline_status in {"success", "partial"} else payload.get("progress", 0)
        payload["current_step"] = "Zakończono" if pipeline_status != "failed" else "Proces zatrzymał się"
        if pipeline_status == "failed":
            errors = re.findall(r"^error=(.+)$", output, flags=re.MULTILINE)
            payload["error"] = errors[-1] if errors else "Pipeline zakończył się błędem. Sprawdź dziennik techniczny."

        if pipeline_status in {"success", "partial"}:
            product_status = "ready" if pipeline_status == "success" else "refresh_recommended"
            set_product_analysis_status(str(payload.get("product_slug", "")), product_status, run_id=run_id)
            if not payload.get("snapshot_updated"):
                payload["error"] = str(payload.get("snapshot_warning", "Research zakończony, ale nie udało się odświeżyć katalogu frontendowego."))
    except subprocess.TimeoutExpired:
        payload.update({"status": "timed_out", "current_step": "Przekroczono limit czasu", "error": f"Pipeline przekroczył limit {RUN_TIMEOUT_SECONDS}s."})
    except (OSError, RuntimeError) as exc:
        payload["status"] = "failed"
        payload["current_step"] = "Proces zatrzymał się"
        payload["error"] = f"Nie udało się uruchomić lokalnego pipeline’u: {exc}"
    finally:
        if process and process.poll() is None:
            terminate_process_group(process)
        payload["child_pid"] = None
        payload["finished_at"] = utc_now()
        terminal = str(payload.get("status", "failed"))
        if terminal in {"failed", "timed_out", "cancelled", "interrupted"}:
            set_product_analysis_status(
                str(payload.get("product_slug", "")),
                terminal if terminal != "failed" else "analysis_failed",
                error=str(payload.get("error", "")),
                run_id=run_id,
            )
        heartbeat_run(payload)
        RUN_COORDINATOR.release_product(run_id)


def start_pipeline_run(
    request: ResearchRequest,
    *,
    retry_of: str | None = None,
    safe_fixture: bool = False,
    inherited_flags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    product_slug = f"{path_slug(request.brand)}__{path_slug(request.model)}"
    group_key = f"{normalized(request.brand)}|{normalized(request.model)}"
    existing_catalog_product = product_for_group_key(group_key)
    try:
        RUN_COORDINATOR.acquire_product(run_id=run_id, product_slug=product_slug, group_key=group_key)
    except LockUnavailableError as exc:
        raise HTTPException(status_code=409, detail="Dla tego produktu działa już inne uruchomienie. Poczekaj na jego zakończenie albo anuluj je.") from exc
    try:
        category_assignment = validate_category_assignment(
            request.category_key or existing_catalog_product.get("category_key", ""),
            request.benchmark_group or existing_catalog_product.get("benchmark_group", ""),
        )
    except CategoryValidationError as exc:
        RUN_COORDINATOR.release_product(run_id)
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "queued",
        "current_step": "W kolejce",
        "progress": 0,
        "started_at": utc_now(),
        "finished_at": None,
        "error": "",
        "logs": [],
        "product_slug": product_slug,
        "group_key": group_key,
        "brand": request.brand,
        "model": request.model,
        "marketplace": "allegro",
        "category_key": category_assignment["category_key"],
        "benchmark_group": category_assignment["benchmark_group"],
        "selected_offer_ids": request.selected_offer_ids,
        "selected_manufacturer_source_ids": request.selected_manufacturer_source_ids,
        "include_manufacturer_sources": request.include_manufacturer_sources,
        "retry_of": retry_of,
        "snapshot_updated": False,
        "last_heartbeat_at": utc_now(),
        "lease_expires_at": lease_until(LEASE_SECONDS),
        "child_pid": None,
        "flags": {"resume": True, "retry": bool(retry_of), "safe_fixture": safe_fixture, **(inherited_flags or {})},
        "run_type": "research",
        "created_at": utc_now(),
    }
    try:
        group = read_json(PROJECT_ROOT / "output" / "model_groups" / product_slug / "group.json", {})
        snapshot_paths: list[str] = []
        for source in group.get("sources", []) if isinstance(group.get("sources", []), list) else []:
            if not isinstance(source, dict):
                continue
            for key in ("content_path", "offer_sections_path", "manufacturer_source_path"):
                value = str(source.get(key, "")).strip()
                if value and value not in snapshot_paths:
                    snapshot_paths.append(value)
        context = RUN_COORDINATOR.create_context(payload, source_snapshot_paths=snapshot_paths)
        payload["run_context_path"] = str((RUN_COORDINATOR.work_directory(run_id) / "context.json").relative_to(PROJECT_ROOT))
        persist_canonical_context(run_id, context, payload)
        payload["work_directory"] = context["working_directory"]
        update_product_state(product_slug, "queued", run_id=run_id)
        save_run(payload)
    except Exception:
        RUN_COORDINATOR.release_product(run_id)
        raise
    if request.include_manufacturer_sources and request.selected_manufacturer_source_ids:
        update_run_log(payload, "Wybrane oficjalne źródła producenta zostaną zweryfikowane z lokalnego cache po pipeline Allegro.")
        save_run(payload)

    # Retry of a run explicitly marked local-only never restarts marketplace
    # search or fetching. It reuses the immutable snapshot context instead.
    if retry_of and (payload["flags"].get("local_only") or payload["flags"].get("no_fetch") or payload["flags"].get("analysis_saved_data")):
        payload["run_type"] = "reanalysis"
        save_run(payload)
        thread = threading.Thread(target=analysis_worker, args=(run_id, product_slug, False), daemon=True, name=f"fieldnote-local-retry-{run_id}")
        thread.start()
        return run_response(payload)

    if retry_of:
        command = [
            sys.executable, str(SCRIPTS_ROOT / "run_model_research_pipeline.py"),
            "--marketplace", "allegro", "--brand", request.brand, "--model", request.model,
            "--category-key", category_assignment["category_key"], "--benchmark-group", category_assignment["benchmark_group"],
            "--apply", "--resume", "--skip-ai", "--retry-errors", "--skip-product-profile",
            "--run-context", str(PROJECT_ROOT / payload["run_context_path"]), "--skip-product-profile",
        ]
    elif safe_fixture:
        fixture_root = RUNS_ROOT / run_id / "fixture"
        fixture_root.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable, str(SCRIPTS_ROOT / "run_model_research_pipeline.py"),
            "--marketplace", "allegro", "--brand", request.brand, "--model", request.model,
            "--category-key", category_assignment["category_key"], "--benchmark-group", category_assignment["benchmark_group"],
            "--fixture-scenario", "success", "--fixture-root", str(fixture_root),
            "--run-context", str(PROJECT_ROOT / payload["run_context_path"]),
        ]
        payload["safe_fixture"] = True
        update_run_log(payload, "Bezpieczny test integracji: użyto lokalnego scenariusza fixture bez API.")
        save_run(payload)
    else:
        command = [
            sys.executable, str(SCRIPTS_ROOT / "run_model_research_pipeline.py"),
            "--marketplace", "allegro", "--brand", request.brand, "--model", request.model,
            "--category-key", category_assignment["category_key"], "--benchmark-group", category_assignment["benchmark_group"],
            "--apply", "--resume", "--run-context", str(PROJECT_ROOT / payload["run_context_path"]), "--skip-product-profile",
        ]
        # A local run without an OpenAI key remains useful: the existing runner
        # updates fetched sources, the benchmark and coverage, while skipping AI.
        if not os.getenv("OPENAI_API_KEY"):
            command.append("--skip-ai")
            payload["ai_mode"] = "skipped_no_local_key"
        else:
            payload["ai_mode"] = "enabled"
        save_run(payload)
    thread = threading.Thread(target=pipeline_worker, args=(run_id, command), daemon=True, name=f"fieldnote-run-{run_id}")
    thread.start()
    return run_response(payload)


@app.get("/api/health")
def health() -> dict[str, bool]:
    return health_payload()


@app.post("/api/research/preview")
def research_preview(request: PreviewRequest) -> dict[str, Any]:
    existing = product_for_group_key(f"{normalized(request.brand)}|{normalized(request.model)}")
    category_key = request.category_key or str(existing.get("category_key", ""))
    benchmark_group = request.benchmark_group or str(existing.get("benchmark_group", ""))
    try:
        validate_category_assignment(category_key, benchmark_group)
    except CategoryValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc

    cache_key = preview_cache_key(request.marketplace, request.brand, request.model, category_key)
    normalized_brand = normalized(request.brand)
    normalized_model = normalized(request.model)
    current_product_slug = f"{path_slug(request.brand)}__{path_slug(request.model)}"
    cached_info = cached_listing_info(request.brand, request.model, request.marketplace, category_key)
    diagnostics = {
        "query": f"{request.brand} {request.model}", "cache_key": cache_key,
        "cache_hit": request.search_mode == "cache", "previous_product_slug": request.previous_product_slug or "",
        "current_product_slug": current_product_slug, "exact_count": 0, "supplementary_count": 0,
        "accessory_count": 0, "probable_count": 0, "titles": [],
    }
    base = {
        "brand": request.brand, "model": request.model, "requested_brand": request.brand,
        "requested_model": request.model, "normalized_brand": normalized_brand,
        "normalized_model": normalized_model, "search_query": f"{request.brand} {request.model}",
        "preview_cache_key": cache_key, "manufacturer_sources": manufacturer_sources_for(request.brand, request.model),
        "preview_diagnostics": diagnostics,
    }

    if request.search_mode == "cache":
        if cached_info is None:
            return {**base, "status": "CACHE_NOT_AVAILABLE", "message": "Brak zapisanych wyników dla tego produktu i kategorii.", "requested_mode": "cache", "result_mode": "cache_not_available", "is_fresh": False, "cached_result_available": False, "offers": [], "summary": {}}
        directory = Path(cached_info["directory"])
        # Historical cache is parsed locally after a classifier upgrade; no
        # network provider is called and its original fetch date is preserved.
        cached_summary = read_json(directory / "research_summary.json", {})
        needs_reparse = not (directory / "extracted_offers.json").is_file() or str(cached_summary.get("match_classification_version", "")) != "3"
        if needs_reparse:
            command = [sys.executable, str(SCRIPTS_ROOT / "fetch_targeted_model_offers.py"), "--marketplace", request.marketplace, "--brand", request.brand, "--model", request.model, "--category-key", category_key, "--input-html", str(directory / "listing.html")]
            completed = run_command(command)
            if completed.returncode != 0:
                return {**base, "status": "CACHE_NOT_AVAILABLE", "message": "Nie udało się odczytać zapisanych wyników.", "requested_mode": "cache", "result_mode": "cache_not_available", "is_fresh": False, "cached_result_available": False, "offers": [], "summary": {}}
            directory = canonical_targeted_dir(request.brand, request.model, request.marketplace)
            cache_listing_artifacts(directory, listing_cache_dir(request.brand, request.model, request.marketplace, category_key), marketplace=request.marketplace, brand=request.brand, model=request.model, category_key=category_key, fetched_at=str(cached_info["cached_at"]))
        offers, summary = read_preview_offers(request.brand, request.model, category_key, directory=directory)
        result_mode, is_fresh, fetched_at = "local_cache", False, str(cached_info["cached_at"])
    else:
        # LIVE deliberately ignores all local listing cache and invokes Firecrawl.
        if not os.getenv("FIRECRAWL_API_KEY"):
            return {**base, "status": "LIVE_SEARCH_FAILED", "message": "Nie udało się pobrać aktualnych ofert.", "requested_mode": "live", "result_mode": "live_failed", "is_fresh": False, "cached_result_available": cached_info is not None, "cached_at": str(cached_info["cached_at"]) if cached_info else "", "offers": [], "summary": {}}
        directory = canonical_targeted_dir(request.brand, request.model, request.marketplace)
        command = [sys.executable, str(SCRIPTS_ROOT / "fetch_targeted_model_offers.py"), "--marketplace", request.marketplace, "--brand", request.brand, "--model", request.model, "--category-key", category_key]
        completed = run_command(command)
        if completed.returncode != 0:
            return {**base, "status": "LIVE_SEARCH_FAILED", "message": "Nie udało się pobrać aktualnych ofert.", "requested_mode": "live", "result_mode": "live_failed", "is_fresh": False, "cached_result_available": cached_info is not None, "cached_at": str(cached_info["cached_at"]) if cached_info else "", "offers": [], "summary": {}}
        fetched_at = cache_listing_artifacts(directory, listing_cache_dir(request.brand, request.model, request.marketplace, category_key), marketplace=request.marketplace, brand=request.brand, model=request.model, category_key=category_key)
        offers, summary = read_preview_offers(request.brand, request.model, category_key, directory=directory)
        result_mode, is_fresh = "live_firecrawl", True

    exact = [offer for offer in offers if offer.get("match_status") == "exact_match"]
    supplementary = [offer for offer in offers if offer.get("source_group") == "supplementary_source"]
    accessories = [offer for offer in offers if offer.get("product_type") == "accessory"]
    probable = [offer for offer in offers if offer.get("match_status") == "probable_match"]
    # A registered identity remains in the catalogue even when this listing has
    # no exact model result. This is lifecycle information, not a deletion.
    if existing and not exact:
        update_product_state(current_product_slug, "refresh_recommended", refresh_reason="insufficient_profile_evidence")
    diagnostics.update({"exact_count": len(exact), "supplementary_count": len(supplementary), "accessory_count": len(accessories), "probable_count": len(probable), "titles": [str(offer.get("title", "")) for offer in offers[:10]]})
    response = {
        **base, "status": "ok", "mode": result_mode, "requested_mode": request.search_mode,
        "result_mode": result_mode, "is_fresh": is_fresh, "fetched_at": fetched_at if is_fresh else "",
        "cached_at": fetched_at if not is_fresh else "", "cached_result_available": True,
        "offers": offers,
        "summary": summary,
    }
    print(json.dumps({"event": "research_preview", **diagnostics}, ensure_ascii=False), flush=True)
    return response


@app.post("/api/research/run")
def research_run(request: ResearchRequest) -> dict[str, Any]:
    # A fully known model may be safely exercised in an isolated runner fixture.
    # Regular UI runs still delegate to the production runner with --resume.
    safe_fixture = False
    return start_pipeline_run(request, safe_fixture=safe_fixture)


@app.post("/api/products/{product_slug}/refresh")
def refresh_product(product_slug: str, request: RefreshRequest) -> dict[str, Any]:
    product_slug = validated_product_slug(product_slug)
    group = read_json(group_dir_for_slug(product_slug) / "group.json", {})
    run_id = str(uuid.uuid4())
    group_key = str(group.get("group_key", ""))
    try:
        RUN_COORDINATOR.acquire_product(run_id=run_id, product_slug=product_slug, group_key=group_key)
    except LockUnavailableError as exc:
        raise HTTPException(status_code=409, detail="Dla tego produktu działa już inne uruchomienie.") from exc
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "queued",
        "current_step": "W kolejce odświeżania",
        "progress": 0,
        "started_at": utc_now(),
        "finished_at": None,
        "error": "",
        "logs": [],
        "product_slug": product_slug,
        "group_key": group_key,
        "brand": str(group.get("brand", "")),
        "model": str(group.get("model", "")),
        "marketplace": "allegro",
        "refresh": {"mode": request.mode},
        "snapshot_updated": False,
        "last_heartbeat_at": utc_now(),
        "lease_expires_at": lease_until(LEASE_SECONDS),
        "child_pid": None,
        "flags": {"refresh_mode": request.mode},
        "run_type": "refresh",
        "created_at": utc_now(),
    }
    try:
        context = RUN_COORDINATOR.create_context(payload, source_snapshot_paths=[])
        payload["run_context_path"] = str((RUN_COORDINATOR.work_directory(run_id) / "context.json").relative_to(PROJECT_ROOT))
        persist_canonical_context(run_id, context, payload)
        payload["work_directory"] = context["working_directory"]
        update_product_state(product_slug, "queued", run_id=run_id)
        save_run(payload)
    except Exception:
        RUN_COORDINATOR.release_product(run_id)
        raise
    thread = threading.Thread(
        target=refresh_worker,
        args=(run_id, product_slug, request.mode),
        daemon=True,
        name=f"fieldnote-refresh-{run_id}",
    )
    thread.start()
    return run_response(payload)


@app.get("/api/products/{product_slug}/analysis-status")
def product_analysis_status(product_slug: str) -> dict[str, Any]:
    """Report local readiness without starting Firecrawl or OpenAI."""
    return analysis_status_payload(validated_product_slug(product_slug))


@app.post("/api/products/{product_slug}/analyze")
def analyze_product(product_slug: str, request: AnalysisRequest) -> dict[str, Any]:
    """Start an analysis run from saved data, optionally refreshing sources."""
    product_slug = validated_product_slug(product_slug)
    group = read_json(group_dir_for_slug(product_slug) / "group.json", {})
    run_id = str(uuid.uuid4())
    group_key = str(group.get("group_key", ""))
    try:
        RUN_COORDINATOR.acquire_product(run_id=run_id, product_slug=product_slug, group_key=group_key)
    except LockUnavailableError as exc:
        raise HTTPException(status_code=409, detail="Dla tego produktu działa już inne uruchomienie.") from exc
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "queued",
        "current_step": "W kolejce analizy",
        "progress": 0,
        "started_at": utc_now(),
        "finished_at": None,
        "error": "",
        "logs": [],
        "product_slug": product_slug,
        "group_key": group_key,
        "brand": str(group.get("brand", "")),
        "model": str(group.get("model", "")),
        "marketplace": "allegro",
        "analysis": {"refresh_sources": request.refresh_sources, "used_sources": []},
        "snapshot_updated": False,
        "last_heartbeat_at": utc_now(),
        "lease_expires_at": lease_until(LEASE_SECONDS),
        "child_pid": None,
        "flags": {"refresh_sources": request.refresh_sources},
        "run_type": "reanalysis",
        "created_at": utc_now(),
    }
    try:
        context = RUN_COORDINATOR.create_context(payload, source_snapshot_paths=[])
        payload["run_context_path"] = str((RUN_COORDINATOR.work_directory(run_id) / "context.json").relative_to(PROJECT_ROOT))
        persist_canonical_context(run_id, context, payload)
        payload["work_directory"] = context["working_directory"]
        update_product_state(product_slug, "queued", run_id=run_id)
        save_run(payload)
    except Exception:
        RUN_COORDINATOR.release_product(run_id)
        raise
    thread = threading.Thread(
        target=analysis_worker,
        args=(run_id, product_slug, request.refresh_sources),
        daemon=True,
        name=f"fieldnote-analysis-{run_id}",
    )
    thread.start()
    return run_response(payload)


@app.get("/api/products/{product_slug}/benchmark")
def product_benchmark(product_slug: str) -> dict[str, Any]:
    return {"schema_version": "1", **benchmark_payload(validated_product_slug(product_slug))}


def competitive_benchmark_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "benchmark_id": str(manifest.get("benchmark_id", "")),
        "title": str(manifest.get("title", "")),
        "status": str(manifest.get("status", "draft")),
        "benchmark_group_key": str(manifest.get("benchmark_group_key", "")),
        "anchor_product_id": str(manifest.get("anchor_product_id", "")),
        "participant_count": len(manifest.get("participant_product_ids", [])),
        "created_at": str(manifest.get("created_at", "")),
        "updated_at": str(manifest.get("updated_at", "")),
    }


def benchmark_product_ref(product: dict[str, Any], *, states: dict[str, dict[str, Any]], links_by_slug: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Resolve a catalog product into the shared, read-only benchmark DTO."""
    brand = str(product.get("brand", "")).strip()
    model = str(product.get("model", "")).strip()
    configuration = str(product.get("configuration", "") or "").strip()
    product_slug = product_slug_for(brand, model, configuration)
    state = states.get(product_slug, {})
    return {
        "product_id": str(product.get("product_id", "")).strip(),
        "brand": brand,
        "model": model,
        "configuration": configuration,
        "benchmark_group": str(product.get("benchmark_group", "")).strip(),
        "product_slug": product_slug,
        "status": public_product_status(state) if state else "refresh_recommended",
        "coverage": coverage_for_group(str(product.get("group_key", group_key_for(brand, model, configuration)))),
        "source_count": len(links_by_slug.get(product_slug, [])),
    }


def benchmark_read_context() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Load the existing catalog/lifecycle read models once for a benchmark response."""
    products = {
        str(product.get("product_id", "")).strip(): product
        for product in load_products()
        if str(product.get("product_id", "")).strip()
    }
    links_by_slug: dict[str, list[dict[str, Any]]] = {}
    for link in read_product_source_links():
        product_slug = str(link.get("product_slug", "")).strip()
        if product_slug:
            links_by_slug.setdefault(product_slug, []).append(link)
    return products, load_product_states(), links_by_slug


def resolve_benchmark_product(product_id: str, *, products: dict[str, dict[str, Any]], states: dict[str, dict[str, Any]], links_by_slug: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product = products.get(product_id)
    if product is None:
        raise BenchmarkValidationError(f"Manifest benchmarku wskazuje nieistniejący produkt: {product_id}.")
    return benchmark_product_ref(product, states=states, links_by_slug=links_by_slug)


def competitive_benchmark_detail(manifest: dict[str, Any]) -> dict[str, Any]:
    products, states, links_by_slug = benchmark_read_context()
    anchor_id = str(manifest.get("anchor_product_id", "")).strip()
    participant_ids = [str(value).strip() for value in manifest.get("participant_product_ids", [])]
    anchor = resolve_benchmark_product(anchor_id, products=products, states=states, links_by_slug=links_by_slug)
    participants = [
        resolve_benchmark_product(product_id, products=products, states=states, links_by_slug=links_by_slug)
        for product_id in participant_ids
    ]
    semantic, price_summary = runtime_semantic_benchmark(str(anchor.get("product_slug", "")), str(manifest.get("benchmark_group_key", "")))
    return {
        "benchmark_id": str(manifest.get("benchmark_id", "")),
        "benchmark_type": "competitive",
        "benchmark_group_key": str(manifest.get("benchmark_group_key", "")),
        "title": str(manifest.get("title", "")),
        "status": str(manifest.get("status", "draft")),
        "anchor": anchor,
        "participants": participants,
        "participant_count": len(participants),
        "created_at": str(manifest.get("created_at", "")),
        "updated_at": str(manifest.get("updated_at", "")),
        "semantic_benchmark": semantic,
        "price_summary": price_summary,
    }


def internal_benchmark_groups() -> dict[str, list[dict[str, Any]]]:
    """Internal comparisons are a dynamic Lionelo catalog view, never manifests."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for product in load_products():
        if normalized_benchmark_brand(product.get("brand")) != "lionelo":
            continue
        group_key = str(product.get("benchmark_group", "")).strip()
        if group_key:
            groups.setdefault(group_key, []).append(product)
    filtered: dict[str, list[dict[str, Any]]] = {}
    for group_key, products in groups.items():
        if len(products) < 2:
            continue
        counts: dict[str, int] = {}
        for product in products:
            config = normalized_benchmark_configuration(product.get("configuration", product.get("stroller_configuration", "")))
            counts[config] = counts.get(config, 0) + 1
        target = sorted(counts, key=lambda key: (-counts[key], key))[0]
        scoped = [product for product in products if normalized_benchmark_configuration(product.get("configuration", product.get("stroller_configuration", ""))) == target]
        if len(scoped) >= 2:
            filtered[group_key] = scoped
    return filtered


def internal_benchmark_label(products: list[dict[str, Any]], group_key: str) -> str:
    for product in products:
        try:
            assignment = validate_category_assignment(product.get("category_key"), group_key)
            label = str(assignment.get("benchmark_group_label", "")).strip()
            if label:
                return label
        except CategoryValidationError:
            continue
        fallback = str(product.get("benchmark_category", "")).strip()
        if fallback:
            return fallback
    return group_key


def internal_benchmark_updated_at(products: list[dict[str, Any]], states: dict[str, dict[str, Any]]) -> str | None:
    timestamps: list[str] = []
    for product in products:
        brand = str(product.get("brand", "")).strip()
        model = str(product.get("model", "")).strip()
        configuration = str(product.get("configuration", "") or "").strip()
        state = states.get(product_slug_for(brand, model, configuration), {})
        timestamp = str(state.get("updated_at") or product.get("updated_at") or product.get("created_at") or "").strip()
        if timestamp:
            timestamps.append(timestamp)
    return max(timestamps) if timestamps else None


@app.post("/api/benchmarks", status_code=201, response_model=CompetitiveBenchmarkDetail)
def create_competitive_benchmark(request: CompetitiveBenchmarkCreateRequest) -> dict[str, Any]:
    try:
        manifest = create_competitive_benchmark_manifest(
            BENCHMARKS_ROOT,
            {"benchmark_type": "competitive", **request.model_dump()},
            load_products(),
        )
    except BenchmarkValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BenchmarkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        return competitive_benchmark_detail(manifest)
    except BenchmarkValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/benchmarks", response_model=list[CompetitiveBenchmarkSummary])
def list_competitive_benchmarks() -> list[dict[str, Any]]:
    return [competitive_benchmark_summary(manifest) for manifest in list_competitive_benchmark_manifests(BENCHMARKS_ROOT)]


@app.get("/api/benchmarks/{benchmark_id}", response_model=CompetitiveBenchmarkDetail)
def get_competitive_benchmark(benchmark_id: str) -> dict[str, Any]:
    try:
        manifest = read_competitive_benchmark_manifest(BENCHMARKS_ROOT, benchmark_id)
    except BenchmarkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return competitive_benchmark_detail(manifest)
    except BenchmarkValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/internal-benchmarks", response_model=list[InternalBenchmarkSummary])
def list_internal_benchmarks() -> list[dict[str, Any]]:
    groups = internal_benchmark_groups()
    return [
        {
            "benchmark_id": None,
            "benchmark_type": "internal",
            "benchmark_group_key": group_key,
            "benchmark_group_label": internal_benchmark_label(products, group_key),
            "title": f"Lionelo: {internal_benchmark_label(products, group_key)}",
            "status": "dynamic",
            "participant_count": len(products),
            "has_comparison": True,
        }
        for group_key, products in sorted(groups.items())
    ]


@app.get("/api/internal-benchmarks/{benchmark_group_key}", response_model=InternalBenchmarkDetail)
def get_internal_benchmark(benchmark_group_key: str) -> dict[str, Any]:
    groups = internal_benchmark_groups()
    products = groups.get(benchmark_group_key)
    if products is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono wewnętrznego benchmarku dla tej grupy.")
    states = load_product_states()
    links_by_slug: dict[str, list[dict[str, Any]]] = {}
    for link in read_product_source_links():
        product_slug = str(link.get("product_slug", "")).strip()
        if product_slug:
            links_by_slug.setdefault(product_slug, []).append(link)
    participants = [benchmark_product_ref(product, states=states, links_by_slug=links_by_slug) for product in products]
    semantic = build_internal_benchmark(runtime_benchmark_products(benchmark_group_key), benchmark_group_key)
    return {
        "benchmark_id": None,
        "benchmark_type": "internal",
        "benchmark_group_key": benchmark_group_key,
        "title": f"Lionelo: {internal_benchmark_label(products, benchmark_group_key)}",
        "status": "dynamic",
        "anchor": None,
        "participants": participants,
        "participant_count": len(participants),
        "created_at": None,
        "updated_at": internal_benchmark_updated_at(products, states),
        "semantic_benchmark": semantic,
        "price_summary": {"status": "no_data", "median": None, "min": None, "max": None, "seller_count": 0},
    }


def catalog_product_payload(product: dict[str, Any], states: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Expose a registered product even before its first research snapshot exists."""
    brand = str(product.get("brand", "")).strip()
    model = str(product.get("model", "")).strip()
    configuration = str(product.get("configuration", "")).strip()
    slug = product_slug_for(brand, model, configuration)
    state = states.get(slug, {})
    status = public_product_status(state) if state else "refresh_recommended"
    try:
        assignment = validate_category_assignment(product.get("category_key"), product.get("benchmark_group"))
    except CategoryValidationError:
        assignment = {"category_label": str(product.get("category", "Wózki dziecięce")), "benchmark_group_label": str(product.get("benchmark_category", ""))}
    return {
        "product_id": str(product.get("product_id", "")),
        "brand": brand,
        "model": model,
        "slug": slug,
        "group_key": str(product.get("group_key", group_key_for(brand, model, configuration))),
        "configuration": configuration,
        "scope": str(product.get("scope", "test")),
        "status": status,
        "status_reason": str(state.get("refresh_reason", "") or "no_research_completed"),
        "status_updated_at": str(state.get("updated_at", "") or product.get("created_at", "")),
        "coverage": None,
        "fields_total": 0,
        "fields_completed": 0,
        "sources_count": 0,
        "missing_fields_count": 0,
        "conflicts_count": 0,
        "updated_at": str(state.get("updated_at", "") or product.get("created_at", "")),
        "marketplaces": [],
        "category": str(assignment.get("category_label") or product.get("category", "Wózki dziecięce")),
        "category_key": str(product.get("category_key", "")),
        "subcategory": str(product.get("subcategory", "")),
        "subcategory_key": str(product.get("subcategory_key", "")),
        "subcategory_label": str(product.get("subcategory", "")),
        "benchmark_group": str(product.get("benchmark_group", "")),
        "benchmark_group_key": str(product.get("benchmark_group_key", product.get("benchmark_group", ""))),
        "benchmark_category": str(assignment.get("benchmark_group_label") or product.get("benchmark_category", "")),
    }


def frontend_catalog() -> list[dict[str, Any]]:
    """Merge immutable snapshots with registered, not-yet-researched products."""
    if DATA_MODE == "supabase":
        return PRODUCT_SERVICE.snapshots.catalog()
    states = load_product_states()
    snapshots = PRODUCT_SERVICE.snapshots.catalog()
    by_slug = {str(item.get("slug", "")): dict(item) for item in snapshots if isinstance(item, dict)}
    merged: list[dict[str, Any]] = []
    for registered in load_products():
        fallback = catalog_product_payload(registered, states)
        slug = fallback["slug"]
        snapshot = by_slug.pop(slug, None)
        if snapshot:
            snapshot.update({key: value for key, value in fallback.items() if not snapshot.get(key) and value not in ("", None, [], {})})
            # Product registry owns taxonomy. Generated snapshots may be older
            # than a category migration and must not reintroduce stale labels.
            for key in (
                "category",
                "category_key",
                "subcategory",
                "subcategory_key",
                "subcategory_label",
                "benchmark_group",
                "benchmark_category",
            ):
                snapshot[key] = fallback[key]
            state = states.get(slug)
            if state:
                snapshot["status"] = public_product_status(state)
                snapshot["status_reason"] = str(state.get("refresh_reason", "") or snapshot.get("status_reason", ""))
                snapshot["status_updated_at"] = str(state.get("updated_at", "") or snapshot.get("status_updated_at", ""))
            merged.append(snapshot)
        else:
            merged.append(fallback)
    merged.extend(by_slug.values())  # Preserve legacy snapshots not yet in the registry.
    return sorted(merged, key=lambda item: (str(item.get("brand", "")).casefold(), str(item.get("model", "")).casefold()))


@app.get("/api/products")
def list_products(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    safe_limit = min(max(int(limit), 1), 500)
    safe_offset = max(int(offset), 0)
    catalog = frontend_catalog()
    return {
        "schema_version": "1",
        "total": len(catalog),
        "limit": safe_limit,
        "offset": safe_offset,
        "items": catalog[safe_offset:safe_offset + safe_limit],
    }


@app.post("/api/products")
def create_product(request: ProductCreateRequest, principal: Principal = Depends(require_data_write)) -> dict[str, Any]:
    """Idempotently register a product before any source preview starts."""
    try:
        assignment = validate_category_assignment(request.category_key, request.benchmark_group)
    except CategoryValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    if DATA_MODE == "supabase":
        repository = PRODUCT_SERVICE.snapshots
        slug = product_slug_for(request.brand, request.model)
        existing = repository.product(slug)
        if existing and (str(existing.get("category_key", "")) != request.category_key or str(existing.get("benchmark_group_key", "")) != request.benchmark_group):
            raise HTTPException(status_code=409, detail="Produkt istnieje już z inną kategorią lub grupą benchmarkową.")
        if existing:
            return {"created": False, "product": existing}
        brand_key = normalized(request.brand).replace(" ", "-")
        repository.upsert_brand(brand_key, request.brand)
        repository.upsert_product({"product_id": f"product:{brand_key}:{path_slug(request.model)}:", "brand": request.brand, "model": request.model, "configuration": "", "product_slug": slug, "group_key": group_key_for(request.brand, request.model), "category_key": request.category_key, "benchmark_group_key": request.benchmark_group, "status": "draft", "is_lionelo": normalized(request.brand) == "lionelo"})
        return {"created": True, "product": repository.product(slug)}
    slug = product_slug_for(request.brand, request.model)
    existing = next((item for item in load_products() if product_slug_for(item.get("brand", ""), item.get("model", "")) == slug), None)
    if existing and (
        str(existing.get("category_key", "")) != request.category_key
        or str(existing.get("benchmark_group", "")) != request.benchmark_group
    ):
        raise HTTPException(status_code=409, detail="Produkt istnieje już z inną kategorią lub grupą benchmarkową.")
    product = ensure_catalog_product(
        request.brand,
        request.model,
        category=assignment["category_label"],
        benchmark_category=assignment["benchmark_group_label"],
        category_key=request.category_key,
        benchmark_group=request.benchmark_group,
        status="refresh_recommended",
    )
    if not existing:
        update_product_state(slug, "refresh_recommended", refresh_reason="no_research_completed")
    record = next((item for item in frontend_catalog() if item.get("slug") == slug), None)
    return {"created": not bool(existing), "product": record or catalog_product_payload(product, load_product_states())}


@app.get("/api/products/{product_slug}")
def get_product(product_slug: str) -> dict[str, Any]:
    product_slug = validated_product_slug(product_slug)
    if DATA_MODE == "supabase":
        payload = PRODUCT_SERVICE.detail(product_slug)
        if not payload:
            raise HTTPException(status_code=404, detail="Nie znaleziono produktu.")
        return {**payload, "schema_version": "1", "fields": [], "sources": [], "research_snapshot_available": False}
    payload = PRODUCT_SERVICE.detail(product_slug)
    catalog_record = next((item for item in frontend_catalog() if item.get("slug") == product_slug), None)
    if not payload and not catalog_record:
        raise HTTPException(status_code=404, detail="Nie znaleziono produktu.")
    if not payload:
        contract = ProductV1(
            product_slug=product_slug,
            group_key=str(catalog_record.get("group_key", "")),
            brand=str(catalog_record.get("brand", "")),
            model=str(catalog_record.get("model", "")),
            status=str(catalog_record.get("status", "refresh_recommended")),
            metrics=None,
        )
        return {**catalog_record, **contract.model_dump(), "fields": [], "sources": [], "research_snapshot_available": False}
    if catalog_record:
        payload = {**payload, **{key: value for key, value in catalog_record.items() if value not in ("", None, [], {})}}
    metrics = load_product_provenance(product_slug).get("metrics", {})
    contract = ProductV1(
        product_slug=product_slug, group_key=str(payload.get("group_key", "")),
        brand=str(payload.get("brand", "")), model=str(payload.get("model", "")),
        status=str(payload.get("status", "")),
        metrics=ProductMetricsV1(**metrics) if isinstance(metrics, dict) and metrics else None,
    )
    return {**payload, **contract.model_dump()}


@app.get("/api/products/{product_slug}/profile", response_model=ProductProfileV1)
def product_profile(product_slug: str) -> ProductProfileV1:
    """Read a cached profile without changing product evidence or benchmark data."""
    product_slug = validated_product_slug(product_slug)
    return ProductProfileV1(**get_profile(product_slug))


@app.get("/api/product-profile/capabilities")
def product_profile_capabilities() -> dict[str, bool]:
    """Expose only whether the opt-in profile action is available, never secrets."""
    return {"ai_enabled": os.getenv("PRODUCT_PROFILE_AI_ENABLED", "").lower() in {"1", "true", "yes"}}


@app.post("/api/products/{product_slug}/profile/generate", response_model=ProductProfileV1)
def generate_profile(product_slug: str) -> ProductProfileV1:
    """One explicit profile request; live generation remains opt-in by env flag."""
    product_slug = validated_product_slug(product_slug)
    if os.getenv("PRODUCT_PROFILE_AI_ENABLED", "").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=409, detail="Generowanie profilu AI jest wyłączone. Ustaw PRODUCT_PROFILE_AI_ENABLED=1.")
    try:
        profile, _ = generate_or_load_profile(product_slug, allow_openai=True)
        if profile.get("profile_status") == "failed":
            code = str(profile.get("generation", {}).get("failure_code", ""))
            status = 422 if code in {"semantic_validation_error", "schema_validation_error"} else 503
            raise HTTPException(status_code=status, detail=str(profile.get("generation", {}).get("failure_reason", "Generowanie profilu nie powiodło się.")))
    except LockUnavailableError as exc:
        raise HTTPException(status_code=409, detail="Generowanie profilu dla tego produktu już trwa.") from exc
    except (PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ProductProfileV1(**profile)


@app.get("/api/products/{product_slug}/metrics", response_model=ProductMetricsV1)
def product_metrics(product_slug: str) -> ProductMetricsV1:
    product_slug = validated_product_slug(product_slug)
    provenance = load_product_provenance(product_slug)
    metrics = provenance.get("metrics", {}) if isinstance(provenance.get("metrics"), dict) else {}
    if not metrics:
        return ProductMetricsV1(
            coverage_percent=None, evidence_quality_percent=None,
            high_confidence_fields=0, weak_fields=0, conflicting_fields=0,
            unattributed_legacy_fields=0, missing_fields=None, analysis_complete=False,
        )
    return ProductMetricsV1(**metrics)


@app.get("/api/sources")
def sources_catalog(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Global source catalogue. It deliberately contains no product assignment."""
    sources = read_source_records()
    sources.sort(key=lambda item: str(item.get("source_id", "")))
    page = paginate(sources, limit, offset)
    return {**page, "sources": page["items"]}


def visual_source_payload(source_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load visual data without exposing local paths to API consumers."""
    if not source_id or "/" in source_id or "\\" in source_id or ".." in source_id:
        raise HTTPException(status_code=400, detail="Nieprawidłowy identyfikator źródła.")
    snapshot_path, blocks_path, media_path = source_visual_paths(source_id)
    if snapshot_path is None or not snapshot_path.exists():
        raise HTTPException(status_code=404, detail="Nie zapisano jeszcze kontekstu wizualnego dla tego źródła.")
    snapshot = read_json(snapshot_path, {})
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=404, detail="Kontekst wizualny jest uszkodzony.")
    blocks = read_visual_jsonl(blocks_path) if blocks_path else []
    media = read_visual_jsonl(media_path) if media_path else []
    def public_artifact(path: object) -> str | None:
        raw = str(path or "").strip()
        if not raw:
            return None
        candidate = (PROJECT_ROOT / raw).resolve()
        allowed = (PROJECT_ROOT / "input").resolve()
        try:
            candidate.relative_to(allowed)
        except ValueError:
            return None
        return artifact_id(raw)
    public_snapshot = {key: value for key, value in snapshot.items() if not key.endswith("_path")}
    public_snapshot["full_page_artifact_id"] = public_artifact(snapshot.get("full_page_screenshot_path"))
    public_snapshot["rendered_html_available"] = bool(snapshot.get("rendered_html_path"))
    for block in blocks:
        section_path = block.pop("section_screenshot_path", None)
        block["section_artifact_id"] = public_artifact(section_path)
    for item in media:
        local_path = item.pop("local_path", None)
        item["local_artifact_id"] = public_artifact(local_path)
    return public_snapshot, blocks, media


@app.get("/api/sources/{source_id}/visuals")
def source_visuals(source_id: str) -> dict[str, Any]:
    snapshot, _blocks, _media = visual_source_payload(source_id)
    return {"schema_version": "1", "snapshot": snapshot}


@app.get("/api/sources/{source_id}/visual-blocks")
def source_visual_blocks(source_id: str, region: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    snapshot, blocks, _media = visual_source_payload(source_id)
    if region:
        blocks = [item for item in blocks if item.get("region") == region]
    return {"source_id": source_id, "visual_snapshot_id": snapshot.get("visual_snapshot_id"), **paginate(blocks, limit, offset)}


@app.get("/api/sources/{source_id}/media")
def source_visual_media(source_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    snapshot, _blocks, media = visual_source_payload(source_id)
    return {"source_id": source_id, "visual_snapshot_id": snapshot.get("visual_snapshot_id"), **paginate(media, limit, offset)}


@app.get("/api/visual-artifacts/{artifact}")
def visual_artifact(artifact: str) -> FileResponse:
    relative = artifact_relative(artifact)
    if not relative:
        raise HTTPException(status_code=400, detail="Nieprawidłowy identyfikator artefaktu.")
    candidate = (PROJECT_ROOT / relative).resolve()
    allowed = (PROJECT_ROOT / "input").resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Artefakt jest poza dozwolonym katalogiem.") from exc
    if not candidate.is_file() or candidate.suffix.casefold() not in {".webp", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=404, detail="Artefakt wizualny nie jest dostępny.")
    return FileResponse(candidate)


@app.get("/api/products/{product_slug}/sources")
def product_sources(
    product_slug: str,
    role: str | None = None,
    fetch_status: str | None = None,
    assignment_status: str | None = None,
    used: bool | None = None,
    source_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Read only explicit ProductSourceLinks without changing data on read."""
    product_slug = validated_product_slug(product_slug)
    payload = linked_product_sources_payload(product_slug)
    records = list(payload["sources"])
    filtered = [
        item for item in records
        if (role is None or item.get("role") == role)
        and (fetch_status is None or item.get("fetch_status") == fetch_status)
        and (assignment_status is None or (item.get("lifecycle", {}).get("link", {}).get("assignment", {}) if isinstance(item.get("lifecycle"), dict) else {}).get("status") == assignment_status)
        and (used is None or bool(item.get("used_in_benchmark")) == used)
        and (source_type is None or item.get("source_type") == source_type)
    ]
    page = paginate(filtered, limit, offset)
    return {**payload, **page, "sources": page["items"]}


@app.get("/api/products/{product_slug}/evidence")
def product_evidence(product_slug: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Serve detailed evidence lazily; the product catalogue stays lightweight."""
    product_slug = validated_product_slug(product_slug)
    provenance = load_product_provenance(product_slug)
    entries: list[dict[str, Any]] = []
    for field_name, field in (provenance.get("fields", {}) if isinstance(provenance.get("fields"), dict) else {}).items():
        if not isinstance(field, dict):
            continue
        for evidence in field.get("evidence_v1", []) if isinstance(field.get("evidence_v1"), list) else []:
            if isinstance(evidence, dict):
                entries.append({"field_name": str(field_name), **evidence})
    entries.sort(key=lambda item: (str(item.get("field_name", "")), str(item.get("evidence_id", ""))))
    return {"product_slug": product_slug, **paginate(entries, limit, offset)}


@app.get("/api/products/{product_slug}/sources/{source_id}/contribution")
def product_source_contribution(product_slug: str, source_id: str) -> dict[str, Any]:
    product_slug = validated_product_slug(product_slug)
    payload = linked_product_sources_payload(product_slug)
    source = next((item for item in payload["sources"] if item.get("source_id") == source_id), None)
    if not isinstance(source, dict):
        raise HTTPException(status_code=404, detail="Nie znaleziono źródła produktu.")
    contribution = source.get("contribution", {})
    if not isinstance(contribution, dict):
        contribution = {}
    summary = {
        "unique_fields_contributed": len(contribution.get("unique_fields_contributed", [])),
        "confirmed_fields": len(contribution.get("confirmed_fields", [])),
        "conflicting_fields": len(contribution.get("conflicting_fields", [])),
        "rejected_evidence": len(contribution.get("rejected_evidence", [])),
        "final_fields_used": len(contribution.get("final_fields_used", [])),
    }
    zero_contribution = not any(summary.values())
    return {
        "schema_version": "1",
        "product_slug": product_slug,
        "source_id": source_id,
        "title": source.get("title", ""),
        "summary": summary,
        "contribution": {**contribution, "new_fields": contribution.get("unique_fields_contributed", [])},
        "zero_contribution": zero_contribution,
        "message": (
            "Źródło zostało pobrane i przeanalizowane, ale nie wniosło nowych ani lepszych danych do finalnego rekordu produktu."
            if zero_contribution else ""
        ),
    }


@app.get("/api/products/{product_slug}/sources/{source_id}/snapshot")
def product_source_snapshot(product_slug: str, source_id: str) -> dict[str, Any]:
    """Serve only a snapshot already linked to this product source."""
    product_slug = validated_product_slug(product_slug)
    payload = linked_product_sources_payload(product_slug)
    source = next((item for item in payload["sources"] if item.get("source_id") == source_id), None)
    if not isinstance(source, dict):
        raise HTTPException(status_code=404, detail="Nie znaleziono źródła produktu.")
    relative_path = str(source.get("clean_snapshot_path") or source.get("raw_snapshot_path") or "").strip()
    if not relative_path:
        raise HTTPException(status_code=404, detail="Nie zapisano lokalnego snapshotu dla tego źródła.")
    snapshot_path = (PROJECT_ROOT / relative_path).resolve()
    try:
        snapshot_path.relative_to(PROJECT_ROOT.resolve())
        content = snapshot_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Lokalny snapshot nie jest dostępny.") from exc
    return {
        "product_slug": product_slug,
        "source_id": source_id,
        "snapshot_path": relative_path,
        "snapshot_type": "technical_clean" if relative_path.endswith("technical_clean.md") else "markdown",
        "content": content,
    }


@app.get("/api/products/{product_slug}/history")
def product_history(product_slug: str) -> dict[str, Any]:
    product_slug = validated_product_slug(product_slug)
    runs = [item for item in list_manifests() if item.get("product_slug") == product_slug]
    runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {"schema_version": "1", "product_slug": product_slug, "total": len(runs), "limit": len(runs), "offset": 0, "items": runs, "history": runs, "runs": runs}


@app.get("/api/products/{product_slug}/history/{version}/snapshot")
def product_history_snapshot(product_slug: str, version: str) -> dict[str, Any]:
    product_slug = validated_product_slug(product_slug)
    if not re.fullmatch(r"[0-9TZ]{8,40}", version):
        raise HTTPException(status_code=404, detail="Nie znaleziono wersji historii.")
    history_dir = group_dir_for_slug(product_slug) / "history" / version
    manifest = read_json(history_dir / "refresh_manifest.json", {})
    state = read_json(history_dir / "result_model_state.json", {})
    if not state:
        state = read_json(history_dir / "model_state.json", {})
    if not manifest and not state:
        raise HTTPException(status_code=404, detail="Nie znaleziono snapshotu tej wersji.")
    fields = state.get("fields", {}) if isinstance(state.get("fields"), dict) else {}
    return {
        "product_slug": product_slug,
        "version": version,
        "manifest": manifest,
        "fields": [
            {
                "field_name": str(name),
                "value": str(item.get("value", "X") or "X"),
                "status": str(item.get("status", "open") or "open"),
            }
            for name, item in fields.items() if isinstance(item, dict)
        ],
    }


@app.get("/api/runs")
def list_runs(
    product_slug: str | None = None,
    status: str | None = None,
    run_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "created_at_desc",
) -> dict[str, Any]:
    if sort != "created_at_desc":
        raise HTTPException(status_code=422, detail="Obsługiwane jest wyłącznie sort=created_at_desc.")
    values = list_manifests()
    if product_slug:
        values = [item for item in values if item.get("product_slug") == product_slug]
    if status:
        values = [item for item in values if item.get("status") == status]
    if run_type:
        values = [item for item in values if item.get("run_type") == run_type]
    page = index_runs(values, index_record, min(max(int(limit), 1), 200), max(int(offset), 0))
    return {**page, "runs": page["items"]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    payload = read_run(run_id)
    return {"schema_version": "1", **payload, "logs_tail": list(payload.get("logs", []))[-80:]}


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict[str, Any]:
    payload = read_run(run_id)
    if payload.get("status") not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Można anulować wyłącznie aktywne uruchomienie.")
    payload["cancel_requested_at"] = utc_now()
    payload["current_step"] = "Trwa anulowanie procesu"
    pid = payload.get("child_pid")
    if process_is_alive(pid):
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except (AttributeError, ProcessLookupError, PermissionError):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    elif payload.get("status") == "queued":
        payload.update({"status": "cancelled", "finished_at": utc_now(), "error": "Run anulowany przed uruchomieniem procesu."})
        set_product_analysis_status(str(payload.get("product_slug", "")), "cancelled", error=str(payload["error"]), run_id=run_id)
        RUN_COORDINATOR.release_product(run_id)
    save_run(payload)
    return run_response(payload)


@app.post("/api/runs/{run_id}/retry")
def retry_run(run_id: str) -> dict[str, Any]:
    previous = read_run(run_id)
    if previous.get("status") not in {"failed", "timed_out", "cancelled", "interrupted"}:
        raise HTTPException(status_code=409, detail="Można ponowić wyłącznie proces ze statusem błąd.")
    context = read_json(CANONICAL_RUNS_ROOT / str(previous.get("run_id", "")) / "context.json", {})
    if not isinstance(context, dict):
        context = {}
    immutable_offers = context.get("selected_offer_ids") if isinstance(context.get("selected_offer_ids"), list) else previous.get("selected_offer_ids", [])
    request = ResearchRequest(
        brand=str(previous.get("brand", "")),
        model=str(previous.get("model", "")),
        category_key=str(previous.get("category_key", "")),
        benchmark_group=str(previous.get("benchmark_group", "")),
        selected_offer_ids=[str(item) for item in immutable_offers],
        include_manufacturer_sources=bool(previous.get("include_manufacturer_sources", True)),
    )
    flags = context.get("flags") if isinstance(context.get("flags"), dict) else previous.get("flags", {})
    return start_pipeline_run(request, retry_of=run_id, inherited_flags=flags if isinstance(flags, dict) else {})


@app.on_event("startup")
def recover_interrupted_runs() -> None:
    """No active run may survive an API restart without a live child process."""
    # Local recovery can be skipped when a damaged historical filesystem would
    # otherwise prevent the read-only browser from starting. No manifests are
    # deleted or rewritten in this mode.
    if os.getenv("FIELDNOTE_SKIP_STARTUP_RECOVERY") == "1":
        print("fieldnote_startup_recovery=skipped", flush=True)
        return
    def read_manifest(path: Path) -> dict[str, Any]:
        value = read_json(path, {})
        return value if isinstance(value, dict) else {}

    def save_manifest(payload: dict[str, Any]) -> None:
        save_run(payload)
        # Preserve the legacy file itself while recording the recovered terminal
        # state, so it cannot be rediscovered as "running" after every restart.
        atomic_write_json(RUNS_ROOT / f"{payload.get('run_id', '')}.json", payload)

    def mark_product(payload: dict[str, Any]) -> None:
        set_product_analysis_status(
            str(payload.get("product_slug", "")),
            "interrupted",
            error=str(payload.get("error", "")),
            run_id=str(payload.get("run_id", "")),
        )

    recovered = RUN_COORDINATOR.recover_orphaned_runs(read_manifest, save_manifest, mark_product)
    # New canonical manifests live in output/runs/<run_id>/ and are not flat
    # files scanned by the P0 coordinator's legacy adapter.
    for payload in list_manifests():
        if payload.get("status") not in {"queued", "running"} or process_is_alive(payload.get("child_pid")):
            continue
        payload.update({
            "status": "interrupted",
            "current_step": "Przerwano po restarcie lokalnego API",
            "error": "Proces potomny nie działa po restarcie API. Możesz ponowić ten run.",
            "finished_at": utc_now(),
            "last_heartbeat_at": utc_now(),
        })
        save_run(payload)
        RUN_COORDINATOR.release_product(str(payload.get("run_id", "")))
        mark_product(payload)
        recovered.append(str(payload.get("run_id", "")))
    if recovered:
        print(f"fieldnote_recovered_runs={len(recovered)}", flush=True)
