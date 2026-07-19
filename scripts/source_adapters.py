"""Offline-first source adapter contract for FIELDNOTE.

Adapters discover and normalise source candidates only.  They never write a
benchmark, model state or source registry; lifecycle services own those
commits.  The included adapters intentionally use local snapshots/fixtures.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from manufacturer_pipeline import NormalizedDocument, read_local_manufacturer_document


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class SourceCandidate:
    source_id: str
    marketplace: str
    source_type: str
    canonical_url: str
    title: str = ""
    offer_id: str | None = None
    confidence: str = "unknown"


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    status: str
    raw_snapshot_path: str | None = None
    clean_snapshot_path: str | None = None
    error: str = ""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 1.0


@dataclass(frozen=True)
class RateLimitPolicy:
    requests_per_minute: int = 0
    burst: int = 0


@dataclass(frozen=True)
class NormalizedSourceContent:
    source_id: str
    title: str
    canonical_url: str
    domain: str
    content_hash: str | None
    raw_snapshot_path: str | None
    clean_snapshot_path: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


# Public aliases keep all adapters on the same input contract.  Evidence is
# deliberately produced downstream by the shared quality/evidence layers.
EvidenceCandidate = dict[str, Any]


class SourceAdapter(Protocol):
    name: str

    def discover(self, query: str, context: dict[str, Any]) -> list[SourceCandidate]: ...
    def fetch(self, source: SourceCandidate, context: dict[str, Any]) -> FetchResult: ...
    def normalize(self, raw_source: SourceCandidate | FetchResult) -> NormalizedSourceContent: ...
    def classify(self, normalized_source: NormalizedSourceContent, product_context: dict[str, Any]) -> dict[str, Any]: ...
    def enrich(self, normalized_source: NormalizedSourceContent) -> dict[str, Any]: ...
    def healthcheck(self) -> dict[str, Any]: ...
    def capabilities(self) -> dict[str, bool]: ...
    def retry_policy(self) -> RetryPolicy: ...
    def rate_limit_policy(self) -> RateLimitPolicy: ...


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


class LocalSnapshotAdapter:
    """Base implementation with a read-only local health/capability contract."""

    name = "local"

    def fetch(self, source: SourceCandidate, context: dict[str, Any]) -> FetchResult:
        return FetchResult(source.source_id, "skipped", error="Adapter lokalny nie pobiera danych z sieci.")

    def classify(self, normalized_source: NormalizedSourceContent, product_context: dict[str, Any]) -> dict[str, Any]:
        model = str(product_context.get("model", "")).casefold()
        return {"model_match": bool(model and model in normalized_source.title.casefold()), "product_type": "unknown"}

    def enrich(self, normalized_source: NormalizedSourceContent) -> dict[str, Any]:
        return {"source_id": normalized_source.source_id, "enriched": False}

    def healthcheck(self) -> dict[str, Any]:
        return {"adapter": self.name, "healthy": True, "network": False}

    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy()

    def rate_limit_policy(self) -> RateLimitPolicy:
        # Zero means "not active" for local/offline adapters.
        return RateLimitPolicy()


class AllegroAdapter(LocalSnapshotAdapter):
    name = "allegro"

    def capabilities(self) -> dict[str, bool]:
        return {"discovery": True, "fetch": False, "seller_enrichment": True, "price": True, "manufacturer_specifications": False, "availability": True, "reviews": False}

    def discover(self, query: str, context: dict[str, Any]) -> list[SourceCandidate]:
        directory = Path(str(context.get("listing_dir", "")))
        records = _read_json(directory / "extracted_offers.json", [])
        result: list[SourceCandidate] = []
        for item in records if isinstance(records, list) else []:
            if not isinstance(item, dict) or not item.get("offer_id"):
                continue
            offer_id = str(item["offer_id"])
            result.append(SourceCandidate(
                source_id=f"allegro:{offer_id}", marketplace="allegro", source_type="marketplace_offer",
                canonical_url=str(item.get("canonical_url", "")), title=str(item.get("title", "")), offer_id=offer_id,
                confidence="high" if item.get("accepted") else "low",
            ))
        return result

    def normalize(self, raw_source: SourceCandidate | FetchResult) -> NormalizedSourceContent:
        if isinstance(raw_source, FetchResult):
            return NormalizedSourceContent(raw_source.source_id, "", "", "", None, raw_source.raw_snapshot_path, raw_source.clean_snapshot_path)
        return NormalizedSourceContent(raw_source.source_id, raw_source.title, raw_source.canonical_url, urlparse(raw_source.canonical_url).netloc, None, None, None)


class ManufacturerAdapter(LocalSnapshotAdapter):
    name = "manufacturer"

    def capabilities(self) -> dict[str, bool]:
        return {"discovery": True, "fetch": False, "seller_enrichment": False, "price": False, "manufacturer_specifications": True, "availability": True, "reviews": False}

    def discover(self, query: str, context: dict[str, Any]) -> list[SourceCandidate]:
        product_slug = str(context.get("product_slug", ""))
        root = ROOT / "input" / "manufacturer_sources"
        candidates: list[SourceCandidate] = []
        for metadata_path in root.glob(f"{product_slug}/*/metadata.json"):
            metadata = _read_json(metadata_path, {})
            if not isinstance(metadata, dict) or metadata.get("model_match") is not True:
                continue
            source_id = str(metadata.get("source_id", metadata_path.parent.name))
            url = str(metadata.get("canonical_url") or metadata.get("source_url") or "")
            candidates.append(SourceCandidate(source_id, "manufacturer", str(metadata.get("source_type", "manufacturer_product_page")), url, str(metadata.get("title", "")), confidence="high"))
        return candidates

    def normalize(self, raw_source: SourceCandidate | FetchResult) -> NormalizedSourceContent:
        if isinstance(raw_source, FetchResult):
            return NormalizedSourceContent(raw_source.source_id, "", "", "", None, raw_source.raw_snapshot_path, raw_source.clean_snapshot_path)
        root = ROOT / "input" / "manufacturer_sources"
        for metadata_path in root.glob("*/*/metadata.json"):
            metadata = _read_json(metadata_path, {})
            if isinstance(metadata, dict) and str(metadata.get("source_id", "")) == raw_source.source_id:
                document: NormalizedDocument = read_local_manufacturer_document(metadata_path.parent)
                return NormalizedSourceContent(
                    document.source_id, document.title, document.canonical_url,
                    urlparse(document.canonical_url).netloc, document.content_hash,
                    str(metadata_path.parent / "raw_response.json"), str(metadata_path.parent / "technical_clean.md"),
                    {"normalized_document": document, "identity_reason": document.identity_reason,
                     "model_match": document.model_match, "facts": [asdict(fact) for fact in document.facts]},
                )
        return NormalizedSourceContent(raw_source.source_id, raw_source.title, raw_source.canonical_url, urlparse(raw_source.canonical_url).netloc, None, None, None, {"model_match": False, "identity_reason": "metadata_not_found"})


class FixtureAdapter(LocalSnapshotAdapter):
    name = "fixture"

    def capabilities(self) -> dict[str, bool]:
        return {"discovery": True, "fetch": True, "seller_enrichment": False, "price": True, "manufacturer_specifications": True, "availability": True, "reviews": True}

    def discover(self, query: str, context: dict[str, Any]) -> list[SourceCandidate]:
        fixture = Path(str(context.get("fixture_path", "")))
        records = _read_json(fixture, [])
        return [SourceCandidate(**item) for item in records if isinstance(item, dict)] if isinstance(records, list) else []

    def normalize(self, raw_source: SourceCandidate | FetchResult) -> NormalizedSourceContent:
        if isinstance(raw_source, FetchResult):
            return NormalizedSourceContent(raw_source.source_id, "", "", "", None, raw_source.raw_snapshot_path, raw_source.clean_snapshot_path)
        return NormalizedSourceContent(raw_source.source_id, raw_source.title, raw_source.canonical_url, urlparse(raw_source.canonical_url).netloc, None, None, None)


def adapter_manifest(adapter: SourceAdapter) -> dict[str, Any]:
    return {"name": adapter.name, "capabilities": adapter.capabilities(), "health": adapter.healthcheck()}


def candidate_dict(candidate: SourceCandidate) -> dict[str, Any]:
    return asdict(candidate)
