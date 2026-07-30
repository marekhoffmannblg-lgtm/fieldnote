"""Offline-first source adapter contract for FIELDNOTE.

Adapters discover and normalise source candidates only.  They never write a
benchmark, model state or source registry; lifecycle services own those
commits.  The included adapters intentionally use local snapshots/fixtures.
"""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from manufacturer_pipeline import NormalizedDocument, read_local_manufacturer_document
from firecrawl_client import FirecrawlClient, FirecrawlError, FirecrawlResponse


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
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    status: str
    raw_snapshot_path: str | None = None
    clean_snapshot_path: str | None = None
    error: str = ""
    content: dict[str, Any] = field(default_factory=dict)


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

    @property
    def provenance(self) -> dict[str, Any]:
        """Stable source metadata shared by all adapters."""
        return {
            "source_id": self.source_id,
            "canonical_url": self.canonical_url,
            "domain": self.domain,
            "content_hash": self.content_hash,
            "raw_snapshot_path": self.raw_snapshot_path,
            "clean_snapshot_path": self.clean_snapshot_path,
            "metadata": dict(self.metadata),
        }


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

    def _normalise_response(self, source: SourceCandidate, response: FirecrawlResponse) -> NormalizedSourceContent:
        payload = response.data
        markdown = str(payload.get("markdown") or payload.get("content") or "")
        title = str(payload.get("title") or source.title or "").strip()
        canonical_url = str(payload.get("url") or source.canonical_url or "").strip()
        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest() if markdown else None
        metadata = {"provider": "firecrawl", "operation": response.operation, "request_id": response.request_id, "attempts": response.attempts, "usage": asdict(response.usage), "status_code": response.status_code, "markdown": markdown, **source.metadata}
        return NormalizedSourceContent(source.source_id, title, canonical_url, urlparse(canonical_url).netloc.lower(), content_hash, None, None, metadata)

    def _normalize_fetch_result(self, raw_source: FetchResult) -> NormalizedSourceContent:
        content = raw_source.content.get("normalized") if isinstance(raw_source.content, dict) else {}
        content = content if isinstance(content, dict) else {}
        metadata = dict(raw_source.content) if isinstance(raw_source.content, dict) else {}
        if "markdown" not in metadata and isinstance(raw_source.content, dict):
            nested = raw_source.content.get("normalized")
            if isinstance(nested, dict) and isinstance(nested.get("metadata"), dict):
                metadata.update(nested["metadata"])
        title = str(content.get("title") or metadata.get("title") or "").strip()
        return NormalizedSourceContent(raw_source.source_id, title, str(content.get("canonical_url", "")), str(content.get("domain", "")), content.get("content_hash"), raw_source.raw_snapshot_path, raw_source.clean_snapshot_path, metadata)

    def firecrawl_fetch(self, source: SourceCandidate, context: dict[str, Any]) -> FetchResult:
        client = context.get("firecrawl_client")
        if not isinstance(client, FirecrawlClient):
            client = FirecrawlClient(max_pages=int(context.get("max_pages", 10) or 10))
        try:
            response = client.scrape(source.canonical_url, cache=context.get("cache_response"))
        except FirecrawlError as exc:
            return FetchResult(source.source_id, "failed", error=str(exc), content={"status_code": exc.status_code, "attempts": exc.attempts})
        normalized = self._normalise_response(source, response)
        return FetchResult(source.source_id, "fetched", clean_snapshot_path=None, content={"normalized": {**normalized.provenance, "title": normalized.title}, "title": normalized.title, "markdown": normalized.metadata.get("markdown", ""), "usage": asdict(response.usage)})


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
            return self._normalize_fetch_result(raw_source)
        return NormalizedSourceContent(raw_source.source_id, raw_source.title, raw_source.canonical_url, urlparse(raw_source.canonical_url).netloc, None, None, None)

    def fetch(self, source: SourceCandidate, context: dict[str, Any]) -> FetchResult:
        return self.firecrawl_fetch(source, context)

    def classify(self, normalized_source: NormalizedSourceContent, product_context: dict[str, Any]) -> dict[str, Any]:
        return classify_source(normalized_source, product_context, source_role="marketplace")


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
            return self._normalize_fetch_result(raw_source)
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

    def fetch(self, source: SourceCandidate, context: dict[str, Any]) -> FetchResult:
        return self.firecrawl_fetch(source, context)

    def classify(self, normalized_source: NormalizedSourceContent, product_context: dict[str, Any]) -> dict[str, Any]:
        result = classify_source(normalized_source, product_context, source_role="manufacturer")
        if normalized_source.metadata.get("normalized_document"):
            result["model_match"] = bool(normalized_source.metadata.get("model_match"))
        return result


class AmazonAdapter(LocalSnapshotAdapter):
    name = "amazon"

    def capabilities(self) -> dict[str, bool]:
        return {"discovery": True, "fetch": True, "seller_enrichment": True, "price": True, "manufacturer_specifications": False, "availability": True, "reviews": False}

    def discover(self, query: str, context: dict[str, Any]) -> list[SourceCandidate]:
        return _discover_fixture_candidates(context, "amazon", query)

    def fetch(self, source: SourceCandidate, context: dict[str, Any]) -> FetchResult:
        return self.firecrawl_fetch(source, context)

    def normalize(self, raw_source: SourceCandidate | FetchResult) -> NormalizedSourceContent:
        if isinstance(raw_source, FetchResult):
            content = raw_source.content.get("normalized") if isinstance(raw_source.content, dict) else {}
            return NormalizedSourceContent(raw_source.source_id, str(content.get("title", "")), str(content.get("canonical_url", "")), str(content.get("domain", "")), content.get("content_hash"), raw_source.raw_snapshot_path, raw_source.clean_snapshot_path, dict(raw_source.content))
        return NormalizedSourceContent(raw_source.source_id, raw_source.title, raw_source.canonical_url, urlparse(raw_source.canonical_url).netloc.lower(), None, None, None, dict(raw_source.metadata))

    def classify(self, normalized_source: NormalizedSourceContent, product_context: dict[str, Any]) -> dict[str, Any]:
        return classify_source(normalized_source, product_context, source_role="marketplace")


class RetailerAdapter(AmazonAdapter):
    name = "retailer"

    def discover(self, query: str, context: dict[str, Any]) -> list[SourceCandidate]:
        return _discover_fixture_candidates(context, "retailers", query)


class FirecrawlSourceAdapter(AmazonAdapter):
    """Generic adapter for a configured Firecrawl source kind."""

    def __init__(self, name: str = "external") -> None:
        self.name = name


def _discover_fixture_candidates(context: dict[str, Any], marketplace: str, query: str) -> list[SourceCandidate]:
    fixture = context.get("fixture_path") or context.get(f"{marketplace}_fixture")
    records = _read_json(Path(str(fixture)), []) if fixture else []
    result: list[SourceCandidate] = []
    for item in records if isinstance(records, list) else []:
        if not isinstance(item, dict) or not item.get("canonical_url"):
            continue
        title = str(item.get("title", ""))
        if query and query.casefold() not in title.casefold() and not item.get("include_always"):
            continue
        result.append(SourceCandidate(str(item.get("source_id") or f"{marketplace}:{hashlib.sha256(str(item['canonical_url']).encode()).hexdigest()[:16]}"), marketplace, str(item.get("source_type") or "marketplace_offer"), str(item["canonical_url"]), title, str(item.get("offer_id")) if item.get("offer_id") else None, str(item.get("confidence") or "fixture"), {k: v for k, v in item.items() if k not in {"source_id", "marketplace", "source_type", "canonical_url", "title", "offer_id", "confidence"}}))
    return result


def classify_source(normalized_source: NormalizedSourceContent, product_context: dict[str, Any], *, source_role: str) -> dict[str, Any]:
    model = _tokens(str(product_context.get("model", "")))
    brand = _tokens(str(product_context.get("brand", "")))
    configuration = _tokens(str(product_context.get("configuration", "")))
    title_text = str(normalized_source.title or "")
    markdown_text = str(normalized_source.metadata.get("markdown", ""))
    text = _tokens(" ".join((title_text, markdown_text)))
    accessory = any(term in " ".join(text) for term in ("accessory", "part", "adapter", "bag", "rain cover", "akcesoria", "czesc")) and not any(term in text for term in ("stroller", "wozek", "spacerowka"))
    brand_match = bool(brand) and all(token in text for token in brand)
    title_tokens = _tokens(title_text)
    model_match = bool(model) and all(token in title_tokens for token in model)
    compatibility_marker = re.search(r"\b(?:compatible\s+with|pasuje\s+do|kompatybiln\w*\s+z|do\s+w[oó]zka)\b", title_text.casefold())
    if model_match and compatibility_marker:
        after_marker = _tokens(title_text[compatibility_marker.end():])
        if all(token in after_marker for token in model):
            model_match = False
    config_match = not configuration or all(token in text for token in configuration)
    return {"source_role": source_role, "brand_match": brand_match, "model_match": model_match, "configuration_match": config_match, "product_type": "accessory" if accessory else ("stroller" if any(term in text for term in ("stroller", "wozek", "spacerowka")) else "unknown"), "quality_gate": "rejected" if accessory or not (brand_match and model_match and config_match) else "accepted"}


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold().replace("²", "2").replace("³", "3"))


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
