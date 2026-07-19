"""Small local API adapter for the existing FIELDNOTE Python pipeline.

This service intentionally delegates all research work to the scripts already
present in the repository.  It listens on localhost only and keeps run state
in small JSON manifests for the Vite frontend to poll.
"""

from __future__ import annotations

import csv
import copy
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

from fastapi import FastAPI, HTTPException
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
from provenance_v1 import load_product_provenance  # noqa: E402
from contracts import ProductMetricsV1, ProductV1  # noqa: E402
from repositories.snapshot_repository import SnapshotRepository  # noqa: E402
from routers.health import health_payload  # noqa: E402
from services.product_service import ProductService  # noqa: E402
from services.run_service import index_runs  # noqa: E402
from services.source_service import paginate  # noqa: E402
RUN_COORDINATOR = RunCoordinator(runs_root=RUNS_ROOT, output_root=PROJECT_ROOT / "output")
PRODUCT_SERVICE = ProductService(SnapshotRepository(FRONTEND_SNAPSHOT_ROOT))
LOCAL_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")
MAX_LOG_LINES = 240
MAX_LOG_CHARS = 18_000
RUN_TIMEOUT_SECONDS = DEFAULT_STAGE_TIMEOUTS["pipeline"]
LABEL_PATTERN = re.compile(r"^[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż .,'&()/-]{1,80}$")
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
PREVIEW_CACHE: dict[str, dict[str, Any]] = {}
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
    allow_headers=["Content-Type"],
)


class PreviewRequest(BaseModel):
    brand: str
    model: str
    marketplace: Literal["allegro"] = "allegro"
    previous_product_slug: str | None = None

    @field_validator("brand", "model")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return validated_label(value)


class ResearchRequest(BaseModel):
    brand: str
    model: str
    selected_offer_ids: list[str] = Field(default_factory=list, max_length=100)
    include_manufacturer_sources: bool = True

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


def preview_cache_key(marketplace: str, brand: str, model: str) -> str:
    """Keep previews isolated by marketplace and the complete requested model."""
    return f"{normalized(marketplace)}|{path_slug(brand)}|{path_slug(model)}"


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
        return value
    # Read-only compatibility for legacy API manifests. Migration preserves the
    # source file but all new writes immediately use output/runs/<id>/.
    legacy_path = RUNS_ROOT / f"{run_id}.json"
    value = read_json(legacy_path, {})
    if isinstance(value, dict) and value:
        return value
    raise HTTPException(status_code=404, detail="Nie znaleziono zapisu uruchomienia.")


def save_run(payload: dict[str, Any]) -> None:
    payload["updated_at"] = utc_now()
    payload["created_at"] = payload.get("created_at") or payload.get("started_at") or utc_now()
    # P0 fixture compatibility: isolated tests replace RUNS_ROOT with a
    # temporary legacy directory. Production keeps this path unchanged and
    # writes only the canonical manifest in output/runs.
    if RUNS_ROOT != API_ROOT / "runs":
        atomic_write_json(RUNS_ROOT / f"{payload['run_id']}.json", payload)
        return
    save_manifest(payload)


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
    return PROJECT_ROOT / "input" / "targeted_search" / f"{path_slug(brand)}__{path_slug(model)}" / marketplace


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


def read_preview_offers(brand: str, model: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    directory = targeted_dir(brand, model)
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
        raw_status = str(raw.get("match_status", "")).strip()
        is_accepted = bool(brand_match and model_match and product_type == "stroller")
        if product_type == "accessory":
            match_status = "rejected"
        elif is_accepted:
            match_status = "exact_match"
        elif raw_status == "uncertain":
            match_status = "uncertain"
        elif brand_match and model_match and product_type != "accessory":
            match_status = "uncertain"
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
                "match_status": match_status,
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
    sources: list[dict[str, Any]] = []
    for group_source in group.get("sources", []):
        if not isinstance(group_source, dict):
            continue
        source_id = str(group_source.get("source_id", ""))
        source = {**group_source, **registry.get(source_id, {})}
        if source.get("marketplace") != "manufacturer":
            continue
        metadata = read_json(PROJECT_ROOT / str(source.get("manufacturer_source_path", "")) / "metadata.json", {})
        model_match = metadata.get("model_match") is True
        raw, clean = local_source_files(source)
        available = bool(raw or clean)
        if available and model_match:
            match_status = "matched"
        elif available:
            match_status = "uncertain"
        else:
            match_status = "unavailable"
        source_type = str(source.get("source_type", "manufacturer_product_page"))
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


def validated_product_slug(product_slug: str) -> str:
    if not PRODUCT_SLUG_PATTERN.fullmatch(product_slug):
        raise HTTPException(status_code=404, detail="Nie znaleziono produktu.")
    group_dir = PROJECT_ROOT / "output" / "model_groups" / product_slug
    if not (group_dir / "group.json").is_file():
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


def benchmark_payload(product_slug: str) -> dict[str, Any]:
    """Return a category-level matrix, never a copy of a single product card."""
    group_dir = group_dir_for_slug(product_slug)
    current_group = read_json(group_dir / "group.json", {})
    category = str(current_group.get("benchmark_category", "")).strip()
    taxonomy_version = str(current_group.get("taxonomy_version", "")).strip()
    taxonomy_ready = str(current_group.get("taxonomy_status", "")) == "classified" and bool(category) and bool(taxonomy_version)
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
            or str(group.get("taxonomy_status", "")) != "classified"
            or str(group.get("benchmark_category", "")).strip() != category
            or str(group.get("taxonomy_version", "")).strip() != taxonomy_version
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
    return {
        "product_slug": product_slug,
        "benchmark_category": category,
        "taxonomy_version": taxonomy_version,
        "taxonomy_status": "classified" if taxonomy_ready else "review_required",
        "current_group_key": current_group_key,
        "models": models,
        "fields": fields_order,
        "has_comparison": len(models) > 1,
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

        if refresh_sources:
            # This is explicitly opt-in. It reuses the existing production runner
            # instead of duplicating targeted-search or fetch logic here.
            command = [
                sys.executable, str(SCRIPTS_ROOT / "run_model_research_pipeline.py"),
                "--marketplace", "allegro", "--brand", str(group.get("brand", "")),
                "--model", str(group.get("model", "")), "--apply", "--resume",
            ]
            result = logged_command(payload, "Odświeżanie źródeł i analiza", 45, command)
            if result.returncode != 0:
                raise RuntimeError("Odświeżanie źródeł i analiza zakończyły się błędem.")
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
            if cascade.returncode != 0:
                raise RuntimeError("Analiza AI zapisanych źródeł zakończyła się błędem.")

        benchmark = logged_command(payload, "Aktualizacja benchmarku", 84, [sys.executable, str(SCRIPTS_ROOT / "build_model_benchmark.py")])
        if benchmark.returncode != 0:
            raise RuntimeError("Nie udało się zaktualizować benchmarku.")
        coverage = logged_command(payload, "Aktualizacja coverage", 91, [sys.executable, str(SCRIPTS_ROOT / "report_model_coverage.py")])
        if coverage.returncode != 0:
            raise RuntimeError("Nie udało się przeliczyć coverage.")
        snapshot = logged_command(payload, "Eksport danych do FIELDNOTE", 97, [sys.executable, str(SCRIPTS_ROOT / "export_frontend_snapshot.py")])
        if snapshot.returncode != 0:
            raise RuntimeError("Nie udało się odświeżyć danych frontendu.")

        after_fields = state_fields(group_dir / "model_state.json")
        changed = changed_fields(before_fields, after_fields)
        coverage_after = coverage_for_group(group_key)
        state_after_path = group_dir / "model_state.json"
        if state_after_path.exists():
            shutil.copy2(state_after_path, history_dir / "result_model_state.json")
        manifest.update({"finished_at": utc_now(), "sources_after": len(group.get("sources", [])), "fields_changed": changed, "coverage_after": coverage_after})
        atomic_write(history_dir / "refresh_manifest.json", manifest)
        payload["analysis"].update({"fields_changed": len(changed), "coverage_after": coverage_after})
        payload.update({"status": "succeeded", "pipeline_status": "success", "current_step": "Analiza zakończona", "progress": 100, "snapshot_updated": True, "finished_at": utc_now()})
        set_product_analysis_status(product_slug, "ready", run_id=run_id)
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
    except (OSError, RuntimeError, ValueError) as exc:
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
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=pipeline_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    payload["child_pid"] = process.pid
    heartbeat_run(payload)
    try:
        stdout, stderr = process.communicate(timeout=RUN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        terminate_process_group(process)
        stdout, stderr = process.communicate()
        raise RuntimeError(f"Etap '{step}' przekroczył limit {RUN_TIMEOUT_SECONDS}s.") from exc
    finally:
        payload["child_pid"] = None
    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    latest = read_run(str(payload.get("run_id", "")))
    if latest.get("cancel_requested_at"):
        raise RunCancelledError("Run został anulowany przez użytkownika.")
    for line in (result.stdout + result.stderr).splitlines():
        update_run_log(payload, f"{step}: {line}")
    heartbeat_run(payload)
    return result


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

        new_offer_ids: list[str] = []
        if mode == "incremental":
            payload["current_step"] = "Wyszukiwanie nowych ofert"
            payload["progress"] = 18
            save_run(payload)
            directory = targeted_dir(str(group.get("brand", "")), str(group.get("model", "")))
            cached_html = directory / "listing.html"
            if cached_html.exists():
                search = logged_command(payload, "Wyszukiwanie nowych ofert (lokalny listing)", 24, [
                    sys.executable, str(SCRIPTS_ROOT / "fetch_targeted_model_offers.py"), "--marketplace", "allegro",
                    "--brand", str(group.get("brand", "")), "--model", str(group.get("model", "")), "--input-html", str(cached_html),
                ])
                if search.returncode != 0:
                    raise RuntimeError("Nie udało się sprawdzić zapisanego listingu ofert.")
                new_offers_path = directory / "new_offers.csv"
                if new_offers_path.exists():
                    with new_offers_path.open(encoding="utf-8", newline="") as handle:
                        new_offer_ids = [str(row.get("external_offer_id", "")).strip() for row in csv.DictReader(handle) if row.get("external_offer_id")]
            elif os.getenv("FIRECRAWL_API_KEY"):
                payload["current_step"] = "Wyszukiwanie nowych ofert przez Firecrawl"
                save_run(payload)
                search = logged_command(payload, "Wyszukiwanie nowych ofert", 24, [
                    sys.executable, str(SCRIPTS_ROOT / "fetch_targeted_model_offers.py"), "--marketplace", "allegro",
                    "--brand", str(group.get("brand", "")), "--model", str(group.get("model", "")),
                ])
                if search.returncode != 0:
                    raise RuntimeError("Nie udało się wyszukać nowych ofert.")
            else:
                update_run_log(payload, "Wyszukiwanie nowych ofert pominięte: brak lokalnego listingu i FIRECRAWL_API_KEY.")

            if new_offer_ids:
                pipeline = [
                    sys.executable, str(SCRIPTS_ROOT / "run_model_research_pipeline.py"), "--marketplace", "allegro",
                    "--brand", str(group.get("brand", "")), "--model", str(group.get("model", "")), "--apply", "--resume",
                ]
                if not os.getenv("OPENAI_API_KEY"):
                    pipeline.append("--skip-ai")
                result = logged_command(payload, "Pobieranie i analiza nowych ofert", 52, pipeline)
                if result.returncode != 0:
                    raise RuntimeError("Pipeline nowych ofert zakończył się błędem.")
            elif changed_sources:
                if not os.getenv("OPENAI_API_KEY"):
                    update_run_log(payload, "Zmodyfikowane źródła wykryto, ale analiza AI została pominięta: brak OPENAI_API_KEY.")
                else:
                    state_path = group_dir / "model_state.json"
                    state = read_json(state_path, {})
                    processed = [item for item in state.get("processed_source_ids", []) if item not in changed_sources]
                    remaining = sorted(set(state.get("remaining_source_ids", [])) | set(changed_sources))
                    state["processed_source_ids"] = processed
                    state["remaining_source_ids"] = remaining
                    atomic_write(state_path, state)
                    result = logged_command(payload, "Analiza zmienionych źródeł", 58, [
                        sys.executable, str(SCRIPTS_ROOT / "extract_model_facts_cascade.py"), "--group-key", group_key, "--resume",
                    ])
                    if result.returncode != 0:
                        raise RuntimeError("Analiza zmienionych źródeł zakończyła się błędem.")
            else:
                # Refresh must complete with an analysis pass even when the local
                # listing contains no new cards. `--resume` keeps this cheap.
                if not os.getenv("OPENAI_API_KEY"):
                    raise RuntimeError("Odświeżenie wymaga OPENAI_API_KEY do automatycznej analizy zapisanych źródeł.")
                result = logged_command(payload, "Analiza zapisanych źródeł", 58, [
                    sys.executable, str(SCRIPTS_ROOT / "extract_model_facts_cascade.py"), "--group-key", group_key, "--resume",
                ])
                if result.returncode != 0:
                    raise RuntimeError("Analiza zapisanych źródeł zakończyła się błędem.")
        else:
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("Pełna ponowna analiza wymaga OPENAI_API_KEY; lokalne snapshoty nie zostały zmienione.")
            result = logged_command(payload, "Pełna ponowna analiza lokalnych snapshotów", 55, [
                sys.executable, str(SCRIPTS_ROOT / "extract_model_facts_cascade.py"), "--group-key", group_key, "--reset-state",
            ])
            if result.returncode != 0:
                raise RuntimeError("Pełna ponowna analiza zakończyła się błędem.")

        benchmark = logged_command(payload, "Aktualizacja benchmarku", 76, [sys.executable, str(SCRIPTS_ROOT / "build_model_benchmark.py")])
        if benchmark.returncode != 0:
            raise RuntimeError("Nie udało się zaktualizować benchmarku.")
        coverage = logged_command(payload, "Aktualizacja coverage", 84, [sys.executable, str(SCRIPTS_ROOT / "report_model_coverage.py")])
        if coverage.returncode != 0:
            raise RuntimeError("Nie udało się przeliczyć coverage.")
        snapshot = logged_command(payload, "Eksport danych do FIELDNOTE", 94, [sys.executable, str(SCRIPTS_ROOT / "export_frontend_snapshot.py")])
        if snapshot.returncode != 0:
            raise RuntimeError("Nie udało się odświeżyć snapshotu frontendu.")

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
        payload.update({"status": "succeeded", "pipeline_status": "success", "current_step": "Odświeżono dane", "progress": 100, "snapshot_updated": True, "finished_at": utc_now()})
        set_product_analysis_status(product_slug, "ready", run_id=run_id)
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
    except (OSError, RuntimeError, ValueError) as exc:
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
        payload["pipeline_status"] = pipeline_status
        payload["status"] = "succeeded" if pipeline_status in {"success", "partial"} else "failed"
        payload["progress"] = 100 if pipeline_status in {"success", "partial"} else payload.get("progress", 0)
        payload["current_step"] = "Zakończono" if pipeline_status != "failed" else "Proces zatrzymał się"
        if pipeline_status == "failed":
            errors = re.findall(r"^error=(.+)$", output, flags=re.MULTILINE)
            payload["error"] = errors[-1] if errors else "Pipeline zakończył się błędem. Sprawdź dziennik techniczny."

        if pipeline_status in {"success", "partial"}:
            product_status = "ready" if pipeline_status == "success" else "refresh_recommended"
            set_product_analysis_status(str(payload.get("product_slug", "")), product_status, run_id=run_id)
            try:
                with global_aggregation_lock(PROJECT_ROOT / "output" / "run_locks", run_id):
                    snapshot = run_command([sys.executable, str(SCRIPTS_ROOT / "export_frontend_snapshot.py")])
            except LockUnavailableError:
                snapshot = subprocess.CompletedProcess([], 1, "", "Inny run aktualizuje snapshot frontendowy.")
            for line in (snapshot.stdout + snapshot.stderr).splitlines():
                update_run_log(payload, f"snapshot: {line}")
            payload["snapshot_updated"] = snapshot.returncode == 0
            if snapshot.returncode != 0:
                payload["error"] = "Research zakończony, ale nie udało się odświeżyć katalogu frontendowego."
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
    try:
        RUN_COORDINATOR.acquire_product(run_id=run_id, product_slug=product_slug, group_key=group_key)
    except LockUnavailableError as exc:
        raise HTTPException(status_code=409, detail="Dla tego produktu działa już inne uruchomienie. Poczekaj na jego zakończenie albo anuluj je.") from exc
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
        "selected_offer_ids": request.selected_offer_ids,
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
    if request.include_manufacturer_sources:
        update_run_log(payload, "Źródła producenta zapisane wcześniej dla tego modelu pozostają dostępne w grupie modelu.")
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
            "--apply", "--resume", "--skip-ai", "--retry-errors",
            "--run-context", str(PROJECT_ROOT / payload["run_context_path"]),
        ]
    elif safe_fixture:
        fixture_root = RUNS_ROOT / run_id / "fixture"
        fixture_root.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable, str(SCRIPTS_ROOT / "run_model_research_pipeline.py"),
            "--marketplace", "allegro", "--brand", request.brand, "--model", request.model,
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
            "--apply", "--resume", "--run-context", str(PROJECT_ROOT / payload["run_context_path"]),
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
    cache_key = preview_cache_key(request.marketplace, request.brand, request.model)
    normalized_brand = normalized(request.brand)
    normalized_model = normalized(request.model)
    current_product_slug = f"{path_slug(request.brand)}__{path_slug(request.model)}"
    cached = PREVIEW_CACHE.get(cache_key)
    if cached is not None:
        response = copy.deepcopy(cached)
        response["preview_diagnostics"]["cache_hit"] = True
        response["preview_diagnostics"]["previous_product_slug"] = request.previous_product_slug or ""
        print(json.dumps({"event": "research_preview", **response["preview_diagnostics"]}, ensure_ascii=False), flush=True)
        return response

    directory = targeted_dir(request.brand, request.model, request.marketplace)
    cached_html = directory / "listing.html"
    command = [
        sys.executable, str(SCRIPTS_ROOT / "fetch_targeted_model_offers.py"),
        "--marketplace", request.marketplace, "--brand", request.brand, "--model", request.model,
    ]
    if cached_html.exists():
        command.extend(["--input-html", str(cached_html)])
        mode = "local_cached_listing"
    elif not os.getenv("FIRECRAWL_API_KEY"):
        raise HTTPException(
            status_code=409,
            detail="Brak zapisanego listingu oraz FIRECRAWL_API_KEY. Dodaj klucz tylko w środowisku lokalnym lub wybierz model z lokalnymi danymi.",
        )
    else:
        mode = "live_firecrawl"
    completed = run_command(command)
    if completed.returncode != 0:
        detail = redact((completed.stderr or completed.stdout).strip())[-700:]
        raise HTTPException(status_code=502, detail=detail or "Nie udało się przygotować podglądu ofert.")
    offers, summary = read_preview_offers(request.brand, request.model)
    exact = [offer for offer in offers if offer.get("match_status") == "exact_match"]
    supplementary = [offer for offer in offers if offer.get("source_group") == "supplementary_source"]
    accessories = [offer for offer in offers if offer.get("product_type") == "accessory"]
    uncertain = [offer for offer in offers if offer.get("match_status") == "uncertain"]
    diagnostics = {
        "query": f"{request.brand} {request.model}",
        "cache_key": cache_key,
        "cache_hit": False,
        "previous_product_slug": request.previous_product_slug or "",
        "current_product_slug": current_product_slug,
        "exact_count": len(exact),
        "supplementary_count": len(supplementary),
        "accessory_count": len(accessories),
        "uncertain_count": len(uncertain),
        "titles": [str(offer.get("title", "")) for offer in offers[:10]],
    }
    response = {
        "status": "ok",
        "mode": mode,
        "brand": request.brand,
        "model": request.model,
        "requested_brand": request.brand,
        "requested_model": request.model,
        "normalized_brand": normalized_brand,
        "normalized_model": normalized_model,
        "search_query": f"{request.brand} {request.model}",
        "preview_cache_key": cache_key,
        "offers": offers,
        "manufacturer_sources": manufacturer_sources_for(request.brand, request.model),
        "summary": summary,
        "preview_diagnostics": diagnostics,
    }
    PREVIEW_CACHE[cache_key] = copy.deepcopy(response)
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


def frontend_catalog() -> list[dict[str, Any]]:
    """Read the generated read-only catalogue without changing pipeline data."""
    return PRODUCT_SERVICE.snapshots.catalog()


@app.get("/api/products")
def list_products(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    safe_limit = min(max(int(limit), 1), 500)
    safe_offset = max(int(offset), 0)
    return PRODUCT_SERVICE.list(safe_limit, safe_offset)


@app.get("/api/products/{product_slug}")
def get_product(product_slug: str) -> dict[str, Any]:
    product_slug = validated_product_slug(product_slug)
    payload = PRODUCT_SERVICE.detail(product_slug)
    if not payload:
        raise HTTPException(status_code=404, detail="Nie wygenerowano jeszcze snapshotu produktu.")
    metrics = load_product_provenance(product_slug).get("metrics", {})
    contract = ProductV1(
        product_slug=product_slug, group_key=str(payload.get("group_key", "")),
        brand=str(payload.get("brand", "")), model=str(payload.get("model", "")),
        status=str(payload.get("status", "")),
        metrics=ProductMetricsV1(**metrics) if isinstance(metrics, dict) and metrics else None,
    )
    return {**payload, **contract.model_dump()}


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
