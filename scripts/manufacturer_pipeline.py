"""Offline manufacturer input preparation for the shared FIELDNOTE pipeline.

This module intentionally stops at :class:`NormalizedDocument`.  Registry,
quality gate, EvidenceItem and final field merge are the same components used
for marketplace sources; no manufacturer-specific finalisation exists here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


NOISE_MARKERS = (
    "cookies", "newsletter", "polecane produkty", "recommended products",
    "znajdź sklep", "dealer locator", "warunki płatności", "menu", "stopka",
)
STOP_MARKERS = ("polecane produkty", "recommended products", "inne modele", "podobne produkty")


@dataclass(frozen=True)
class DeterministicFact:
    field_candidate: str
    raw_value: str
    normalized_value: str
    excerpt: str
    source_id: str
    section: str
    extraction_method: str


@dataclass(frozen=True)
class NormalizedDocument:
    source_id: str
    source_type: str
    authority: str
    canonical_url: str
    title: str
    model_match: bool
    identity_reason: str
    clean_text: str
    content_hash: str
    facts: tuple[DeterministicFact, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", unescape(str(value or "")).lower()).strip()


def exact_model_match(title: str, model: str) -> bool:
    wanted = normalized(model)
    return bool(wanted and re.search(rf"(?:^|\s){re.escape(wanted)}(?:$|\s)", normalized(title)))


def official_domain(url: str, brand: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    slug = normalized(brand).replace(" ", "")
    # Brand-owned hostname is a deterministic first-pass rule.  A manually
    # persisted metadata record may supply a stronger official-domain verdict.
    return bool(host and slug and slug in host.replace("-", ""))


def clean_manufacturer_text(text: str) -> str:
    """Retain technical product content and cut navigation/recommendations."""
    kept: list[str] = []
    for raw in unescape(text).splitlines():
        line = raw.strip()
        lowered = line.lower()
        if any(marker in lowered for marker in STOP_MARKERS):
            break
        if not line or any(marker in lowered for marker in NOISE_MARKERS):
            continue
        if re.fullmatch(r"https?://\S+", line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _fact(field_name: str, value: str, excerpt: str, source_id: str, method: str) -> DeterministicFact:
    return DeterministicFact(field_name, value, value.strip(), excerpt[:300], source_id, "technical", method)


def extract_deterministic_facts(text: str, source_id: str, json_ld: Any = None) -> tuple[DeterministicFact, ...]:
    facts: list[DeterministicFact] = []
    patterns = (
        ("Waga", r"(?:waga(?: produktu)?|weight)\s*[:\-]?\s*([0-9]+(?:[,.][0-9]+)?\s*kg)"),
        ("Udźwig", r"(?:maksymalne obciążenie|udźwig|do)\s*[:\-]?\s*([0-9]+(?:[,.][0-9]+)?\s*kg)"),
        ("Wymiary po złożeniu", r"(?:po złożeniu|wymiary po złożeniu)\s*[:\-]?\s*([0-9]+\s*[x×]\s*[0-9]+(?:\s*[x×]\s*[0-9]+)?\s*cm)"),
    )
    for name, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            facts.append(_fact(name, match.group(1), match.group(0), source_id, "regex"))
    if isinstance(json_ld, dict):
        for key in ("sku", "gtin", "gtin13", "mpn"):
            value = str(json_ld.get(key, "") or "").strip()
            if value:
                facts.append(_fact(key.upper(), value, f"{key}: {value}", source_id, "json_ld"))
    return tuple(facts)


def normalized_document_from_fixture(metadata: dict[str, Any], raw_text: str, *, source_id: str | None = None) -> NormalizedDocument:
    sid = str(source_id or metadata.get("source_id") or "manufacturer:fixture").strip()
    title = str(metadata.get("title") or "").strip()
    brand = str(metadata.get("brand") or "").strip()
    model = str(metadata.get("model") or "").strip()
    url = str(metadata.get("canonical_url") or metadata.get("source_url") or "").strip()
    cleaned = clean_manufacturer_text(raw_text)
    # Metadata is a discovery hint, not proof.  The exact model must survive
    # in the cleaned page itself so a stale title cannot validate another card.
    match = bool(metadata.get("model_match") is True and exact_model_match(cleaned, model))
    reason = "exact_brand_model_on_official_page" if match and official_domain(url, brand) else "model_or_official_domain_mismatch"
    warnings: list[str] = []
    if not match:
        warnings.append("identity_mismatch_blocks_extraction")
    facts = extract_deterministic_facts(cleaned, sid, metadata.get("json_ld")) if match else ()
    return NormalizedDocument(
        source_id=sid,
        source_type=str(metadata.get("source_type") or "manufacturer_product_page"),
        authority="manufacturer",
        canonical_url=url,
        title=title,
        model_match=match,
        identity_reason=reason,
        clean_text=cleaned,
        content_hash=hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
        facts=facts,
        warnings=tuple(warnings),
    )


def read_local_manufacturer_document(directory: Path) -> NormalizedDocument:
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    text_path = directory / "technical_clean.md"
    if not text_path.exists():
        text_path = directory / "document_text.md"
    if not text_path.exists():
        text_path = directory / "markdown.md"
    raw = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
    return normalized_document_from_fixture(metadata if isinstance(metadata, dict) else {}, raw)
