"""Strict, source-backed ProductProfileV1 generation for FIELDNOTE.

No product facts are written here. A profile is an optional narrative artifact
over immutable evidence, sources, and visual context.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import base64
import sys
import uuid
from copy import deepcopy
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from p0_runtime import FileLock, LockUnavailableError, atomic_write_json
from benchmark_taxonomy import product_profile_identity
from product_profile_prompt import (
    PRODUCT_PROFILE_MODEL,
    PRODUCT_PROFILE_PROMPT_VERSION,
    PRODUCT_PROFILE_SCHEMA_VERSION,
    SYSTEM_PROMPT,
    product_profile_response_schema,
)
from provenance_v1 import load_product_provenance
from visual_snapshots import read_jsonl, source_visual_paths

ROOT = Path(__file__).resolve().parent.parent
PROFILE_ROOT = ROOT / "output" / "product_profiles"
SCHEMA_VERSION = "1"
PROFILE_VERSION = "v1"
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PROFILE_IMAGE_TOTAL_BYTES = 16 * 1024 * 1024


class ProviderNested(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderTheme(ProviderNested):
    theme_id: str; title: str; summary: str; basis_types: list[str]
    supporting_evidence_ids: list[str]
    supporting_visual_block_ids: list[str]; supporting_media_ids: list[str]
    confidence: Literal["high", "medium", "low"]


class ProviderMarketplace(ProviderNested):
    observation: str; supporting_evidence_ids: list[str]
    confidence: Literal["high", "medium", "low"]


class ProviderVisual(ProviderNested):
    observation: str; basis: Literal["explicit_image_text", "caption", "visual_scene", "repetition", "mixed", "text_context_only"]
    visual_access: Literal["image_seen", "text_context_only"]
    supporting_visual_block_ids: list[str]; supporting_media_ids: list[str]
    confidence: Literal["high", "medium", "low"]; is_factual_product_claim: Literal[False]


class ProviderConflict(ProviderNested):
    summary: str; field_names: list[str]; supporting_evidence_ids: list[str]


class ProviderUnknown(ProviderNested):
    summary: str; reason: str; related_source_ids: list[str]


class ProviderStructuredOutput(ProviderNested):
    one_sentence_summary: str = Field(min_length=1, max_length=280)
    narrative_summary: str = Field(min_length=1050, max_length=1500)
    discovered_themes: list[ProviderTheme] = Field(max_length=6)
    marketplace_narrative: list[ProviderMarketplace]
    visual_positioning: list[ProviderVisual]
    important_conflicts: list[ProviderConflict] = Field(max_length=3)
    important_unknowns: list[ProviderUnknown] = Field(max_length=3)


class ProviderProfileError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostic: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostic = diagnostic or {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def profile_cache_key(
    input_hash: str,
    *,
    prompt_version: str = PRODUCT_PROFILE_PROMPT_VERSION,
    schema_version: str = PRODUCT_PROFILE_SCHEMA_VERSION,
    model_name: str = PRODUCT_PROFILE_MODEL,
) -> str:
    """Return the versioned cache identity for one exact model input."""
    return _hash({
        "input_hash": input_hash,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "model_name": model_name,
    })


def _snippet(value: object, length: int = 300) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:length]


def profile_path(product_slug: str, root: Path = PROFILE_ROOT) -> Path:
    return root / f"{product_slug}.json"


def diagnostic_path(product_slug: str, root: Path = PROFILE_ROOT) -> Path:
    return root / f"{product_slug}.provider_response_diagnostic.json"


def parsed_output_path(product_slug: str, root: Path = PROFILE_ROOT) -> Path:
    return root / f"{product_slug}.provider_structured_output.json"


def rejected_output_path(product_slug: str, root: Path = PROFILE_ROOT) -> Path:
    return root / f"{product_slug}.provider_structured_output_rejected.json"


def normalized_candidate_rejected_path(product_slug: str, root: Path = PROFILE_ROOT) -> Path:
    return root / f"{product_slug}.normalized_candidate_rejected.json"


def attempt_path(product_slug: str, root: Path = PROFILE_ROOT) -> Path:
    """Keep a failed generation attempt separate from the last good profile."""
    return root / f"{product_slug}.generation_attempt.json"


def stable_visual_block_id(source_id: str, position: int, heading: object, content: object) -> str:
    basis = "|".join((source_id, str(position), _snippet(heading, 180), _snippet(content, 600)))
    return "visual:block:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def _source_summary(source: dict[str, Any]) -> dict[str, str]:
    return {
        "source_id": str(source.get("source_id", "")),
        "marketplace": str(source.get("marketplace", "")),
        "content_family_id": str(source.get("content_family_id", "")),
    }


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"[ąćęłńóśźż]", lambda match: {"ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ź": "z", "ż": "z"}[match.group(0)], str(value or "").lower())).strip("-")


def _product_identity(payload: dict[str, Any]) -> dict[str, str]:
    """Build product identity from persisted taxonomy, never from model prose."""
    category = str(payload.get("category", "") or "")
    benchmark_category = str(payload.get("benchmark_category", "") or "")
    product_type = str(payload.get("product_type", "") or "")
    taxonomy_version = str(payload.get("taxonomy_version", "") or "v1")
    taxonomy = product_profile_identity(category, benchmark_category, taxonomy_version)
    if not product_type:
        product_type = str(taxonomy["product_type"])
    taxonomy_category_id = str(payload.get("taxonomy_category_id", "") or taxonomy["taxonomy_category_id"])
    brand = str(payload.get("brand", "") or "")
    model = str(payload.get("model", "") or "")
    return {
        "brand": brand,
        "model": model,
        "product_name": str(payload.get("product_name", "") or f"{brand} {model}".strip()),
        "product_type": product_type,
        "benchmark_category": benchmark_category,
        "taxonomy_category_id": taxonomy_category_id,
        "category": category,
    }


def deterministic_factual_highlights(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Facts are immutable neutral projections of canonical input only."""
    return [
        {
            "statement": f"{item['field_name']}: {item['value']}",
            "field_names": [str(item["field_name"])],
            "supporting_evidence_ids": list(item["supporting_evidence_ids"]),
        }
        for item in data.get("facts", [])
        if isinstance(item, dict) and item.get("field_name") and item.get("value") and item.get("supporting_evidence_ids")
        and item.get("field_status") == "valid" and item.get("claim_kind") == "objective"
    ]


def _canonical_input(payload: dict[str, Any]) -> dict[str, Any]:
    """The only input shape used by dry-run, request, cache and review."""
    evidence = [item for item in payload.get("evidence", []) if isinstance(item, dict) and item.get("evidence_id") and item.get("source_id") and item.get("excerpt")][:10]
    blocks: list[dict[str, Any]] = []
    for position, item in enumerate(payload.get("visual_blocks", [])):
        if not isinstance(item, dict):
            continue
        heading = _snippet(item.get("heading", ""), 140)
        content = _snippet(item.get("text_context", item.get("text", "")), 280)
        source_id = str(item.get("source_id", ""))
        if not source_id or not heading or heading.lower() == "opis":
            continue
        block_id = str(item.get("visual_block_id", "") or "")
        if not block_id or block_id == source_id:
            block_id = stable_visual_block_id(source_id, position, heading, content)
        blocks.append({
            "visual_block_id": block_id, "source_id": source_id, "heading": heading,
            "text_context": content, "media_ids": [str(value) for value in item.get("media_ids", []) if str(value)],
            "local_media_available": bool(item.get("local_media_available", item.get("has_local_media", False))),
            "basis": "local_media_and_text_context" if item.get("local_media_available", item.get("has_local_media", False)) else "text_context_only",
        })
        if len(blocks) == 8:
            break
    block_media_ids = {item for block in blocks for item in block["media_ids"]}
    media = []
    for item in payload.get("media", []):
        if not isinstance(item, dict) or str(item.get("media_id", "")) not in block_media_ids:
            continue
        # The canonical input carries metadata only for local files deliberately
        # selected for transmission; URLs and paths are never included.
        if not item.get("byte_size"):
            continue
        media.append({"media_id": str(item["media_id"]), "source_id": str(item.get("source_id", "")), "visual_block_ids": [block["visual_block_id"] for block in blocks if str(item["media_id"]) in block["media_ids"]], "mime_type": str(item.get("mime_type", "")), "alt_text": _snippet(item.get("alt_text", ""), 160), "byte_size": int(item["byte_size"]), "sha256": str(item.get("sha256", item.get("content_hash", "")))})
    sent_media_ids = {item["media_id"] for item in media}
    for block in blocks:
        block["media_ids"] = [item for item in block["media_ids"] if item in sent_media_ids]
        block["local_media_available"] = bool(block["media_ids"])
        block["basis"] = "local_media_and_text_context" if block["local_media_available"] else "text_context_only"
    selected_source_ids = {str(item["source_id"]) for item in evidence} | {str(item["source_id"]) for item in blocks}
    source_lookup = {str(item.get("source_id", "")): item for item in payload.get("sources", []) if isinstance(item, dict)}
    evidence_families = {str(item["source_id"]): str(item.get("content_family_id", "")) for item in evidence if item.get("content_family_id")}
    sources = []
    for source_id in sorted(selected_source_ids):
        if source_id not in source_lookup:
            continue
        source = _source_summary(source_lookup[source_id])
        source["content_family_id"] = source["content_family_id"] or evidence_families.get(source_id, "")
        sources.append(source)
    # A source selected by evidence but absent from historical source metadata
    # remains an explicit source identity, never silently dropped.
    known = {item["source_id"] for item in sources}
    sources.extend({"source_id": item, "marketplace": "", "content_family_id": ""} for item in sorted(selected_source_ids - known))
    facts = []
    for item in payload.get("facts", []):
        if not isinstance(item, dict) or not str(item.get("field_name", "")) or str(item.get("value", "")) == "X":
            continue
        ids = [str(value) for value in item.get("supporting_evidence_ids", []) if str(value) in {entry["evidence_id"] for entry in evidence}]
        if ids:
            facts.append({"field_name": str(item["field_name"]), "value": str(item["value"]), "supporting_evidence_ids": ids, "field_status": str(item.get("field_status", "valid")), "claim_kind": str(item.get("claim_kind", "objective"))})
    source_families = {str(item.get("content_family_id", "")) for item in evidence if item.get("content_family_id")}
    summary = {
        "sources_used": len(sources),
        "manufacturer_sources": sum(item["marketplace"] == "manufacturer" for item in sources),
        "marketplace_sources": sum(bool(item["marketplace"]) and item["marketplace"] != "manufacturer" for item in sources),
        "independent_content_families": len(source_families),
        "evidence_items_used": len(evidence),
        "visual_blocks_used": len(blocks),
        "media_items_used": len(media),
        "textual_coverage": "partial" if evidence else "none",
        "visual_coverage": "full" if media else "partial" if blocks else "none",
    }
    identity = _product_identity(payload)
    canonical = {
        "schema_version": SCHEMA_VERSION, "prompt_version": PRODUCT_PROFILE_PROMPT_VERSION,
        "model_name": PRODUCT_PROFILE_MODEL, "product_slug": str(payload.get("product_slug", "")),
        **identity,
        "sources": sources, "facts": facts, "evidence": evidence,
        "conflicts": [item for item in payload.get("conflicts", []) if isinstance(item, dict)][:3],
        "visual_blocks": blocks, "media": media, "input_summary": summary,
        "transmission_boundary": "Use only this ProductProfileInput. Do not use information outside it.",
    }
    canonical["canonical_input_hash"] = _hash({key: value for key, value in canonical.items() if key not in {"canonical_input_hash", "transmission_payload_hash", "cache_key", "prompt_version", "model_name"}})
    canonical["cache_key"] = profile_cache_key(canonical["canonical_input_hash"])
    return canonical


def build_profile_input(product_slug: str, *, max_images: int = 8) -> dict[str, Any]:
    group = read_json(ROOT / "output" / "model_groups" / product_slug / "group.json", {})
    state = read_json(ROOT / "output" / "model_groups" / product_slug / "model_state.json", {})
    provenance = load_product_provenance(product_slug)
    sources = [item for item in group.get("sources", []) if isinstance(item, dict)] if isinstance(group, dict) else []
    fields = provenance.get("fields", {}) if isinstance(provenance, dict) else {}
    if not fields and isinstance(state, dict): fields = state.get("fields", {})
    evidence: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for field_name, field in fields.items() if isinstance(fields, dict) else []:
        if not isinstance(field, dict): continue
        value = str(field.get("value", "X") or "X")
        items = field.get("evidence_v1", field.get("evidence", [])); items = items if isinstance(items, list) else [items]
        ids: list[str] = []
        accepted = []
        for item in items:
            if not isinstance(item, dict): continue
            status = str(item.get("evidence_status", item.get("validation_status", field.get("validation_status", ""))))
            excerpt = _snippet(item.get("excerpt", item.get("evidence", "")), 300)
            source_id = str(item.get("source_id", ""))
            if status != "valid" or str(field.get("status", "")) not in {"confirmed", "valid"} or not excerpt or not source_id: continue
            evidence_id = str(item.get("evidence_id") or "evidence:" + _hash([product_slug, field_name, source_id, excerpt])[:24])
            record = {"field_name": str(field_name), "value": str(item.get("value", value) or value), "evidence_id": evidence_id, "source_id": source_id, "content_family_id": str(item.get("content_family_id", "")), "excerpt": excerpt, "evidence_status": status, "validation_status": str(item.get("validation_status", field.get("validation_status", ""))), "source_authority": str(item.get("source_authority", ""))}
            evidence.append(record); accepted.append(record); ids.append(evidence_id)
        field_status = "valid" if str(field.get("status", "")) == "confirmed" and str(field.get("validation_status", "valid")) in {"valid", ""} else str(field.get("status", ""))
        claim_kind = "marketing" if re.search(r"(?i)wygodn|komfort|idealn|najlepsz|praktyczn", value) else "objective"
        if value != "X" and ids: facts.append({"field_name": str(field_name), "value": value, "supporting_evidence_ids": ids, "field_status": field_status, "claim_kind": claim_kind})
        aggregate = field.get("provenance", field.get("aggregate", {}))
        if str(field.get("status", "")) == "conflicting" or isinstance(aggregate, dict) and aggregate.get("has_conflict"):
            conflicts.append({"field_name": str(field_name), "evidence": accepted})
    raw_blocks: list[dict[str, Any]] = []
    raw_media: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source.get("source_id", "")); _snapshot, blocks_file, media_file = source_visual_paths(source_id, product_slug)
        media_by_id = {str(item.get("media_id", "")): item for item in read_jsonl(media_file) if isinstance(item, dict)} if media_file else {}
        if not blocks_file: continue
        for position, block in enumerate(read_jsonl(blocks_file)):
            if not isinstance(block, dict) or str(block.get("region", "")) in {"recommendation", "navigation"}: continue
            heading = _snippet(block.get("heading", ""), 140); content = _snippet(" ".join(str(block.get(key, "")) for key in ("caption", "text")), 280)
            if not heading or any(token in f"{heading} {content}".lower() for token in ("polecane", "sponsorowane", "podobne produkty", "rekomendowane")): continue
            ids = [str(item) for item in block.get("media_ids", []) if str(item) in media_by_id]
            raw_blocks.append({"visual_block_id": str(block.get("visual_block_id", "") or stable_visual_block_id(source_id, position, heading, content)), "source_id": source_id, "heading": heading, "text_context": content, "media_ids": ids, "local_media_available": False})
            for media_id in ids:
                item = media_by_id[media_id]; local = str(item.get("local_path", "") or "")
                candidate = Path(local) if local else None
                if candidate and not candidate.is_absolute(): candidate = ROOT / candidate
                if candidate and candidate.is_file(): raw_media.append({"media_id": media_id, "source_id": source_id, "mime_type": str(item.get("mime_type", "")), "alt_text": _snippet(item.get("alt_text", item.get("title", "")), 160), "byte_size": candidate.stat().st_size, "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()})
            if len(raw_blocks) >= max_images: break
    raw = {"product_slug": product_slug, "brand": str(group.get("brand", state.get("brand", ""))), "model": str(group.get("model", state.get("model", ""))), "product_name": f"{group.get('brand', state.get('brand', ''))} {group.get('model', state.get('model', ''))}".strip(), "category": str(group.get("category", "")), "benchmark_category": str(group.get("benchmark_category", "")), "taxonomy_version": str(group.get("taxonomy_version", "")), "sources": [_source_summary(item) for item in sources], "facts": facts, "evidence": evidence, "conflicts": conflicts, "visual_blocks": raw_blocks, "media": raw_media}
    return _canonical_input(raw)


def transmission_profile_input(payload: dict[str, Any], payload_hash: str) -> dict[str, Any]:
    # Preserve the approved payload itself, but canonicalise its selected items
    # so cache/diagnostics and model input have one consistent representation.
    canonical = _canonical_input(payload)
    canonical["transmission_payload_hash"] = payload_hash
    return canonical


def _base_profile(data: dict[str, Any], status: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "profile_id": f"profile:{data['product_slug']}", "product_slug": data["product_slug"], "profile_status": status, "profile_version": PROFILE_VERSION, "one_sentence_summary": "", "narrative_summary": "", "discovered_themes": [], "factual_highlights": deterministic_factual_highlights(data), "marketplace_narrative": [], "visual_positioning": [], "important_conflicts": [], "important_unknowns": [], "input_summary": data["input_summary"], "generation": {"canonical_input_hash": data["canonical_input_hash"], "transmission_payload_hash": str(data.get("transmission_payload_hash", "")), "cache_key": data["cache_key"], "model_name": PRODUCT_PROFILE_MODEL, "prompt_version": PRODUCT_PROFILE_PROMPT_VERSION, "schema_version": PRODUCT_PROFILE_SCHEMA_VERSION, "openai_requests_attempted_this_run": 0, "openai_requests_succeeded_this_run": 0, "profile_request_count_total": 0, "cached": False, "generated_at": "", "failure_code": "", "failure_reason": "", "semantic_profile_nonempty": False, "profile_quality_valid": False}}


def has_profile_material(data: dict[str, Any]) -> bool:
    """Return whether canonical or effective input contains profile material."""
    summary = data.get("input_summary", {}) if isinstance(data.get("input_summary"), dict) else {}
    return any(int(summary.get(key, 0) or 0) > 0 for key in (
        "evidence_items_used", "visual_blocks_used", "media_items_used",
    ))


def insufficient_evidence_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Return an unsaved non-generated result without calling a provider."""
    profile = _base_profile(data, "not_generated")
    profile["generation"].update({
        "failure_code": "insufficient_profile_evidence",
        "failure_reason": "Brak materiału źródłowego do wygenerowania profilu produktu.",
        "openai_requests_attempted_this_run": 0,
        "openai_requests_succeeded_this_run": 0,
        "profile_quality_valid": False,
    })
    return profile


def _provider_dynamic_id_error_details(result: object, data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or not isinstance(data, dict):
        return []
    allowed = {
        "supporting_evidence_ids": {str(item.get("evidence_id", "")) for item in data.get("evidence", []) if isinstance(item, dict)},
        "supporting_visual_block_ids": {str(item.get("visual_block_id", "")) for item in data.get("visual_blocks", []) if isinstance(item, dict)},
        "supporting_media_ids": {str(item.get("media_id", "")) for item in data.get("media", []) if isinstance(item, dict)},
        "related_source_ids": {str(item.get("source_id", "")) for item in data.get("sources", []) if isinstance(item, dict)},
    }
    references = {
        "discovered_themes": ("supporting_evidence_ids", "supporting_visual_block_ids", "supporting_media_ids"),
        "marketplace_narrative": ("supporting_evidence_ids",),
        "visual_positioning": ("supporting_visual_block_ids", "supporting_media_ids"),
        "important_conflicts": ("supporting_evidence_ids",),
        "important_unknowns": ("related_source_ids",),
    }
    errors: list[dict[str, Any]] = []
    for section, fields in references.items():
        items = result.get(section, [])
        if not isinstance(items, list):
            continue
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            for field_name in fields:
                values = item.get(field_name, [])
                if not isinstance(values, list):
                    continue
                for value_index, value in enumerate(values):
                    if str(value) not in allowed[field_name]:
                        errors.append({
                            "section": section,
                            "item_index": item_index,
                            "loc": [section, str(item_index), field_name, str(value_index)],
                            "type": "enum",
                            "message": f"Nieznany identyfikator dla {field_name}.",
                        })
    return errors


def validate_profile_response_schema(result: object, data: dict[str, Any] | None = None) -> list[str]:
    """Validate the provider-owned DTO before it is mapped to public fields."""
    return list(dict.fromkeys(
        f"schema_validation_error:{detail['section']}"
        for detail in _provider_schema_error_details(result, data)
    ))


def validate_final_profile_sections_schema(result: object) -> list[str]:
    """Validate mapped sections against the actual public ProductProfileV1."""
    api_root = str(ROOT / "fieldnote-api")
    if api_root not in sys.path:
        sys.path.insert(0, api_root)
    from contracts import ProductProfileV1

    try:
        ProductProfileV1.model_validate({"product_slug": "schema-check", **(result if isinstance(result, dict) else {})})
    except ValidationError as exc:
        return [f"schema_validation_error:{entry['loc'][0]}" for entry in exc.errors()]
    return []


def _provider_schema_error_details(result: object, data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        ProviderStructuredOutput.model_validate(result)
    except ValidationError as exc:
        details = []
        for item in exc.errors():
            loc = list(item.get("loc", ()))
            section = str(loc[0]) if loc else "root"
            item_index = next((value for value in loc if isinstance(value, int)), None)
            details.append({"section": section, "item_index": item_index, "loc": [str(value) for value in loc], "type": str(item.get("type", "")), "message": str(item.get("msg", ""))})
        return details
    return _provider_dynamic_id_error_details(result, data)


_UNSUPPORTED_FACTUAL_INTERPRETATIONS = re.compile(
    r"(?i)\b(zapewnia|zwiększa|zwieksza|ułatwia|ulatwia|podnosi|czyni)\b|\b(wytrzymałość|wytrzymalosc|mobilność|mobilnosc|komfort|użyteczność|uzytecznosc|praktyczn)"
)
_TEXT_ONLY_VISUAL_LANGUAGE = re.compile(r"(?i)(na zdjęciu|na zdjeciu|widać|widac|wizualizacja pokazuje|materiały wizualne przedstawiają|materialy wizualne przedstawiaja)")
_DIRECT_NEGATIVE_PRODUCT_CLAIM = re.compile(r"(?iu)\bprodukt\b\s+nie\s+(?:ma|posiada)\b")


def _profile_text(profile: dict[str, Any]) -> str:
    parts = [str(profile.get("one_sentence_summary", "")), str(profile.get("narrative_summary", ""))]
    for section in ("discovered_themes", "factual_highlights", "marketplace_narrative", "visual_positioning", "important_conflicts", "important_unknowns"):
        for item in profile.get(section, []) if isinstance(profile.get(section), list) else []:
            if isinstance(item, dict): parts.extend(str(value) for value in item.values() if isinstance(value, str))
    return " ".join(parts).casefold()


def _identity_errors(profile: dict[str, Any], data: dict[str, Any]) -> list[str]:
    taxonomy = product_profile_identity(str(data.get("category", "")), str(data.get("benchmark_category", "")))
    expected_type = str(taxonomy["product_type"])
    if expected_type == "unknown" or expected_type != str(data.get("product_type", "unknown")):
        return []
    text = _profile_text(profile)
    hits = [str(marker).casefold() for marker in taxonomy["exclusive_terms"] if str(marker).casefold() in text]
    return ["semantic_validation_error:product_identity_mismatch"] if hits else []


def _typed_reference_errors(profile: dict[str, Any], data: dict[str, Any]) -> list[str]:
    sources = {str(item.get("source_id", "")) for item in data["sources"]}
    evidence = {str(item.get("evidence_id", "")) for item in data["evidence"]}
    blocks = {str(item.get("visual_block_id", "")): str(item.get("source_id", "")) for item in data["visual_blocks"]}
    media = {str(item.get("media_id", "")): str(item.get("source_id", "")) for item in data["media"]}
    families = {
        str(item.get("content_family_id", ""))
        for item in [*data["sources"], *data["evidence"]]
        if isinstance(item, dict) and item.get("content_family_id")
    }
    errors: list[str] = []

    def check(values: object, allowed: set[str], code: str) -> None:
        ids = [str(value) for value in values] if isinstance(values, list) else []
        if any(value not in allowed for value in ids): errors.append(code)

    for item in profile.get("discovered_themes", []):
        if not isinstance(item, dict): continue
        source_ids = {str(value) for value in item.get("supporting_source_ids", [])} if isinstance(item.get("supporting_source_ids"), list) else set()
        block_ids = item.get("supporting_visual_block_ids", []) if isinstance(item.get("supporting_visual_block_ids"), list) else []
        media_ids = item.get("supporting_media_ids", []) if isinstance(item.get("supporting_media_ids"), list) else []
        check(item.get("supporting_source_ids"), sources, "semantic_validation_error:theme_source_id")
        check(item.get("supporting_evidence_ids"), evidence, "semantic_validation_error:theme_evidence_id")
        check(block_ids, set(blocks), "semantic_validation_error:theme_visual_block_id")
        check(media_ids, set(media), "semantic_validation_error:theme_media_id")
        if (block_ids or media_ids) and not source_ids:
            errors.append("semantic_validation_error:theme_source_id")
        for block_id in block_ids:
            if block_id in blocks and blocks[block_id] not in source_ids:
                errors.append("semantic_validation_error:theme_visual_block_source_mismatch")
        for media_id in media_ids:
            if media_id in media and media[media_id] not in source_ids:
                errors.append("semantic_validation_error:theme_media_source_mismatch")
    for item in profile.get("marketplace_narrative", []):
        if not isinstance(item, dict): continue
        check(item.get("supporting_source_ids"), sources, "semantic_validation_error:marketplace_source_id")
        check(item.get("content_family_ids"), families, "semantic_validation_error:marketplace_content_family_id")
    for item in profile.get("visual_positioning", []):
        if not isinstance(item, dict): continue
        source_ids = {str(value) for value in item.get("supporting_source_ids", [])} if isinstance(item.get("supporting_source_ids"), list) else set()
        check(item.get("supporting_source_ids"), sources, "semantic_validation_error:visual_source_id")
        check(item.get("supporting_visual_block_ids"), set(blocks), "semantic_validation_error:visual_block_id")
        check(item.get("supporting_media_ids"), set(media), "semantic_validation_error:visual_media_id")
        referenced_blocks = item.get("supporting_visual_block_ids", []) if isinstance(item.get("supporting_visual_block_ids"), list) else []
        referenced_media = item.get("supporting_media_ids", []) if isinstance(item.get("supporting_media_ids"), list) else []
        if (referenced_blocks or referenced_media) and not source_ids:
            errors.append("semantic_validation_error:visual_source_id")
        for block_id in referenced_blocks:
            if block_id in blocks and blocks[block_id] not in source_ids: errors.append("semantic_validation_error:visual_block_source_mismatch")
        for media_id in referenced_media:
            if media_id in media and media[media_id] not in source_ids: errors.append("semantic_validation_error:visual_media_source_mismatch")
    for item in profile.get("important_conflicts", []):
        if not isinstance(item, dict): continue
        check(item.get("supporting_source_ids"), sources, "semantic_validation_error:conflict_source_id")
        check(item.get("supporting_evidence_ids"), evidence, "semantic_validation_error:conflict_evidence_id")
    for item in profile.get("important_unknowns", []):
        if not isinstance(item, dict): continue
        check(item.get("related_source_ids"), sources, "semantic_validation_error:unknown_source_id")
    return errors


def validate_profile_against_input(profile: dict[str, Any], data: dict[str, Any]) -> list[str]:
    errors = validate_final_profile_sections_schema({key: profile.get(key) for key in product_profile_response_schema()["required"]})
    if errors: return errors
    evidence_ids = {str(item.get("evidence_id", "")) for item in data["evidence"]}
    source_ids = {str(item.get("source_id", "")) for item in data["sources"]}
    block_ids = {str(item.get("visual_block_id", "")) for item in data["visual_blocks"]}
    media_ids = {str(item.get("media_id", "")) for item in data["media"]}
    analytic = ("discovered_themes", "marketplace_narrative", "visual_positioning")
    if not any(profile.get(key) for key in analytic): errors.append("semantic_validation_error:empty_profile")
    errors.extend(_identity_errors(profile, data))
    errors.extend(_typed_reference_errors(profile, data))
    summary = str(profile.get("one_sentence_summary", "")).strip()
    if not summary:
        errors.append("semantic_validation_error:one_sentence_empty")
    elif len(summary.split()) > 35:
        errors.append("semantic_validation_error:one_sentence_length")
    words = len(profile["narrative_summary"].split())
    if not 120 <= words <= 220: errors.append("semantic_validation_error:narrative_length")
    if len(profile["discovered_themes"]) > 6 or len(profile["important_conflicts"]) > 3 or len(profile["important_unknowns"]) > 3: errors.append("semantic_validation_error:section_limit")
    if profile.get("factual_highlights") != deterministic_factual_highlights(data):
        errors.append("semantic_validation_error:deterministic_factual_highlights")
        if any(_UNSUPPORTED_FACTUAL_INTERPRETATIONS.search(str(item.get("statement", ""))) for item in profile.get("factual_highlights", []) if isinstance(item, dict)):
            errors.append("unsupported_factual_interpretation")
    for item in profile["discovered_themes"]:
        if not isinstance(item, dict) or not str(item.get("title", "")).strip() or not str(item.get("summary", "")).strip(): errors.append("semantic_validation_error:theme_content"); continue
        ids = set(map(str, item.get("supporting_source_ids", []))) | set(map(str, item.get("supporting_evidence_ids", []))) | set(map(str, item.get("supporting_visual_block_ids", []))) | set(map(str, item.get("supporting_media_ids", [])))
        if not ids: errors.append("semantic_validation_error:theme_support")
    for item in profile["marketplace_narrative"]:
        ids = set(map(str, item.get("supporting_source_ids", []))) if isinstance(item, dict) else set()
        if not isinstance(item, dict) or not str(item.get("observation", "")).strip() or not ids:
            errors.append("semantic_validation_error:marketplace_support")
    for item in profile["visual_positioning"]:
        if not isinstance(item, dict) or item.get("is_factual_product_claim") is not False: errors.append("semantic_validation_error:visual_factual"); continue
        ids = set(map(str, item.get("supporting_visual_block_ids", []))) | set(map(str, item.get("supporting_media_ids", [])))
        if not ids: errors.append("semantic_validation_error:visual_support")
        if not item.get("supporting_media_ids") and item.get("basis") != "text_context_only": errors.append("semantic_validation_error:visual_without_media")
        if data["input_summary"]["media_items_used"] == 0 and item.get("visual_access") != "text_context_only": errors.append("semantic_validation_error:visual_without_media")
        if item.get("visual_access") == "text_context_only" and _TEXT_ONLY_VISUAL_LANGUAGE.search(str(item.get("observation", ""))): errors.append("semantic_validation_error:visual_seen_claim")
    claim_text = " ".join([
        str(profile.get("one_sentence_summary", "")),
        str(profile.get("narrative_summary", "")),
        *(str(item.get("summary", "")) for item in profile.get("discovered_themes", []) if isinstance(item, dict)),
        *(str(item.get("observation", "")) for item in profile.get("marketplace_narrative", []) if isinstance(item, dict)),
    ])
    if _DIRECT_NEGATIVE_PRODUCT_CLAIM.search(claim_text):
        errors.append("semantic_validation_error:negative_missing_inference")
    return sorted(set(errors))


def _response_diagnostic(data: dict[str, Any]) -> dict[str, Any]:
    return {"request_id": "", "model_name": PRODUCT_PROFILE_MODEL, "prompt_version": PRODUCT_PROFILE_PROMPT_VERSION, "schema_version": PRODUCT_PROFILE_SCHEMA_VERSION, "provider_status": "", "finish_reason": "", "refusal_present": False, "output_text_present": False, "structured_output_present": False, "parsed_output_present": False, "parser_error": "", "schema_error": "", "semantic_error": "", "semantic_validation_errors": [], "narrative_word_count": 0, "invalid_references": [], "rejected_output_path": "", "rejected_output_saved": False, "token_usage": {}, "response_received_at": "", "canonical_input_hash": data["canonical_input_hash"], "transmission_payload_hash": str(data.get("transmission_payload_hash", "")), "cache_key": data["cache_key"]}


def _model_owned_output(profile: dict[str, Any]) -> dict[str, Any]:
    """Persist only parsed structured fields, never transport metadata or media."""
    return {key: profile.get(key) for key in product_profile_response_schema()["required"]}


def _invalid_reference_details(profile: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = {
        "source_id": {str(item.get("source_id", "")) for item in data.get("sources", []) if isinstance(item, dict)},
        "evidence_id": {str(item.get("evidence_id", "")) for item in data.get("evidence", []) if isinstance(item, dict)},
        "visual_block_id": {str(item.get("visual_block_id", "")) for item in data.get("visual_blocks", []) if isinstance(item, dict)},
        "media_id": {str(item.get("media_id", "")) for item in data.get("media", []) if isinstance(item, dict)},
        "content_family_id": {str(item.get("content_family_id", "")) for item in [*data.get("sources", []), *data.get("evidence", [])] if isinstance(item, dict) and item.get("content_family_id")},
    }
    reference_keys = {"supporting_source_ids": "source_id", "related_source_ids": "source_id", "supporting_evidence_ids": "evidence_id", "supporting_visual_block_ids": "visual_block_id", "supporting_media_ids": "media_id", "content_family_ids": "content_family_id"}
    details: list[dict[str, Any]] = []
    for section in ("discovered_themes", "marketplace_narrative", "visual_positioning", "important_conflicts", "important_unknowns"):
        for index, item in enumerate(profile.get(section, []) if isinstance(profile.get(section), list) else []):
            if not isinstance(item, dict):
                continue
            for key, kind in reference_keys.items():
                for reference_id in item.get(key, []) if isinstance(item.get(key), list) else []:
                    reference_id = str(reference_id)
                    if reference_id not in allowed[kind]:
                        details.append({"section": section, "item_index": index, "reference_type": kind, "reference_id": reference_id, "reason": "unknown_reference_id"})
    return details


def _relative_output_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def _write_rejected_outputs(
    product_slug: str,
    raw_result: dict[str, Any] | None,
    normalized_candidate: dict[str, Any] | None,
    diagnostic: dict[str, Any],
    data: dict[str, Any],
    *,
    root: Path,
) -> None:
    if isinstance(raw_result, dict):
        raw_path = rejected_output_path(product_slug, root)
        atomic_write_json(raw_path, raw_result)
        diagnostic.update({"rejected_output_path": _relative_output_path(raw_path), "rejected_output_saved": True})
    if isinstance(normalized_candidate, dict):
        normalized_path = normalized_candidate_rejected_path(product_slug, root)
        atomic_write_json(normalized_path, normalized_candidate)
        diagnostic["normalized_candidate_rejected_path"] = _relative_output_path(normalized_path)
    if isinstance(normalized_candidate, dict):
        diagnostic.update({
            "narrative_word_count": len(str(normalized_candidate.get("narrative_summary", "")).split()),
            "invalid_references": _invalid_reference_details(normalized_candidate, data),
        })


def _extract_structured_output(payload: dict[str, Any], data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    diagnostic = _response_diagnostic(data); diagnostic.update({"request_id": str(payload.get("id", "")), "provider_status": str(payload.get("status", "")), "token_usage": payload.get("usage", {}) if isinstance(payload.get("usage"), dict) else {}, "response_received_at": utc_now()})
    output_text = str(payload.get("output_text", "") or "")
    refusal = False
    finish_reason = ""
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(item, dict): continue
        finish_reason = finish_reason or str(item.get("finish_reason", ""))
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if not isinstance(content, dict): continue
            if content.get("type") == "refusal" or content.get("refusal"): refusal = True
            if content.get("type") == "output_text" and content.get("text") and not output_text: output_text = str(content["text"])
    diagnostic.update({"finish_reason": finish_reason, "refusal_present": refusal, "output_text_present": bool(output_text), "structured_output_present": bool(output_text)})
    if refusal: raise ProviderProfileError("provider_refusal", "Provider odmówił wygenerowania profilu.", diagnostic)
    if str(payload.get("status", "")) in {"incomplete", "failed"}:
        raise ProviderProfileError("provider_incomplete_response", "Provider nie ukończył structured output.", diagnostic)
    if not output_text.strip(): raise ProviderProfileError("provider_empty_response", "Provider nie zwrócił structured output.", diagnostic)
    try: result = json.loads(output_text)
    except json.JSONDecodeError as exc:
        diagnostic["parser_error"] = str(exc); raise ProviderProfileError("structured_output_parse_error", "Structured output nie jest poprawnym JSON.", diagnostic) from exc
    diagnostic["parsed_output_present"] = True
    return result, diagnostic


def _approved_media_files(data: dict[str, Any]) -> list[tuple[dict[str, Any], Path]]:
    """Resolve only media IDs already present in the approved canonical input."""
    approved = {str(item.get("media_id", "")): item for item in data.get("media", []) if isinstance(item, dict)}
    selected: list[tuple[dict[str, Any], Path]] = []
    for source_id in {str(item.get("source_id", "")) for item in approved.values()}:
        _snapshot, _blocks, media_file = source_visual_paths(source_id, str(data.get("product_slug", "")))
        for record in read_jsonl(media_file) if media_file else []:
            media_id = str(record.get("media_id", "")) if isinstance(record, dict) else ""
            approved_item = approved.get(media_id)
            if not approved_item:
                continue
            mime_type = str(approved_item.get("mime_type", record.get("mime_type", ""))).lower()
            local = Path(str(record.get("local_path", "")))
            if not local.is_absolute(): local = ROOT / local
            if mime_type not in ALLOWED_IMAGE_MIME_TYPES or not local.is_file() or local.stat().st_size > MAX_PROFILE_IMAGE_BYTES:
                continue
            selected.append((approved_item, local))
    return selected


def _matches_image_mime(content: bytes, mime_type: str) -> bool:
    signatures = {
        "image/png": b"\x89PNG\r\n\x1a\n",
        "image/jpeg": b"\xff\xd8\xff",
        "image/webp": b"RIFF",
    }
    expected = signatures.get(mime_type)
    if not expected or not content.startswith(expected):
        return False
    return mime_type != "image/webp" or content[8:12] == b"WEBP"


def build_openai_request(data: dict[str, Any], *, media_files: list[tuple[dict[str, Any], Path]] | None = None) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Build a Responses payload with only approved local media as data URLs."""
    attachments = media_files if media_files is not None else _approved_media_files(data)
    effective = deepcopy(data)
    sent_ids: list[str] = []
    sent_hashes: set[str] = set()
    total_bytes = 0
    for item, path in attachments:
        media_id = str(item.get("media_id", ""))
        mime_type = str(item.get("mime_type", "")).lower()
        try:
            path.resolve().relative_to((ROOT / "input").resolve())
        except ValueError:
            continue
        size = path.stat().st_size if path.is_file() else 0
        image_bytes = path.read_bytes() if size else b""
        content_hash = hashlib.sha256(image_bytes).hexdigest() if size else ""
        expected_hash = str(item.get("sha256", item.get("content_hash", "")) or "")
        if expected_hash and expected_hash != content_hash:
            raise ProviderProfileError("approved_media_changed", f"Zatwierdzony obraz {media_id} zmienił się po preflight.")
        if not media_id or mime_type not in ALLOWED_IMAGE_MIME_TYPES or not path.is_file() or not _matches_image_mime(image_bytes, mime_type) or size > MAX_PROFILE_IMAGE_BYTES or total_bytes + size > MAX_PROFILE_IMAGE_TOTAL_BYTES or content_hash in sent_hashes or len(sent_ids) >= 8:
            continue
        sent_hashes.add(content_hash); total_bytes += size
        sent_ids.append(media_id)
    effective["media"] = [item for item in data.get("media", []) if isinstance(item, dict) and str(item.get("media_id", "")) in set(sent_ids)]
    covered_blocks = sum(bool(set(block.get("media_ids", [])) & set(sent_ids)) for block in effective.get("visual_blocks", []) if isinstance(block, dict))
    block_count = len([block for block in effective.get("visual_blocks", []) if isinstance(block, dict)])
    coverage = "full" if block_count and covered_blocks == block_count else "partial" if covered_blocks or block_count else "none"
    effective["input_summary"] = {**data["input_summary"], "media_items_used": len(sent_ids), "visual_coverage": coverage}
    for block in effective.get("visual_blocks", []):
        if not isinstance(block, dict): continue
        block["media_ids"] = [media_id for media_id in block.get("media_ids", []) if media_id in sent_ids]
        block["local_media_available"] = bool(block["media_ids"])
        block["basis"] = "local_media_and_text_context" if block["local_media_available"] else "text_context_only"
    # The text payload describes exactly the media that is attached below.
    content: list[dict[str, Any]] = [{"type": "input_text", "text": json.dumps(effective, ensure_ascii=False)}]
    for item, path in attachments:
        media_id = str(item.get("media_id", ""))
        mime_type = str(item.get("mime_type", "")).lower()
        if media_id not in sent_ids or mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            continue
        content.append({"type": "input_text", "text": f"Obraz media_id={media_id}. Analizuj tylko ten załączony obraz."})
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "input_image", "image_url": f"data:{mime_type};base64,{encoded}"})
    body = {"model": PRODUCT_PROFILE_MODEL, "input": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}], "text": {"format": {"type": "json_schema", "name": "product_profile_v1", "strict": True, "schema": product_profile_response_schema(effective)}}}
    return body, effective, sent_ids


def _profile_from_model_result(data: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    profile = _base_profile(data, "generated")
    sources_by_id = {str(item.get("source_id")): item for item in data.get("sources", []) if isinstance(item, dict)}
    evidence_by_id = {str(item.get("evidence_id")): item for item in data.get("evidence", []) if isinstance(item, dict)}
    blocks_by_id = {str(item.get("visual_block_id")): item for item in data.get("visual_blocks", []) if isinstance(item, dict)}
    media_by_id = {str(item.get("media_id")): item for item in data.get("media", []) if isinstance(item, dict)}

    def unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    def relations(item: dict[str, Any]) -> tuple[list[str], list[str]]:
        source_ids, families = [], []
        for evidence_id in item.get("supporting_evidence_ids", []):
            evidence = evidence_by_id.get(str(evidence_id), {})
            source_ids.append(str(evidence.get("source_id", ""))); families.append(str(evidence.get("content_family_id", "")))
        for block_id in item.get("supporting_visual_block_ids", []): source_ids.append(str(blocks_by_id.get(str(block_id), {}).get("source_id", "")))
        for media_id in item.get("supporting_media_ids", []): source_ids.append(str(media_by_id.get(str(media_id), {}).get("source_id", "")))
        source_ids = unique(source_ids)
        # Families are backend-owned provenance. Provider-supplied family IDs
        # are intentionally discarded and rebuilt from accepted relations.
        families.extend(str(sources_by_id.get(source_id, {}).get("content_family_id", "")) for source_id in source_ids)
        return source_ids, unique(families)

    # Explicit DTO-to-public-contract mapping. Provider source IDs are ignored.
    profile["one_sentence_summary"] = str(result["one_sentence_summary"])
    profile["narrative_summary"] = str(result["narrative_summary"])
    profile["discovered_themes"] = []
    for item in result["discovered_themes"]:
        source_ids, _families = relations(item)
        profile["discovered_themes"].append({"theme_id": str(item["theme_id"]), "title": str(item["title"]), "summary": str(item["summary"]), "basis_types": list(item["basis_types"]), "supporting_source_ids": source_ids, "supporting_evidence_ids": list(item["supporting_evidence_ids"]), "supporting_visual_block_ids": list(item["supporting_visual_block_ids"]), "supporting_media_ids": list(item["supporting_media_ids"]), "confidence": str(item["confidence"])})
    profile["marketplace_narrative"] = []
    for item in result["marketplace_narrative"]:
        source_ids, families = relations(item)
        profile["marketplace_narrative"].append({"observation": str(item["observation"]), "supporting_source_ids": source_ids, "content_family_ids": families, "confidence": str(item["confidence"])})
    profile["visual_positioning"] = []
    for item in result["visual_positioning"]:
        source_ids, _families = relations(item)
        profile["visual_positioning"].append({"observation": str(item["observation"]), "basis": str(item["basis"]), "visual_access": str(item["visual_access"]), "supporting_visual_block_ids": list(item["supporting_visual_block_ids"]), "supporting_media_ids": list(item["supporting_media_ids"]), "supporting_source_ids": source_ids, "confidence": str(item["confidence"]), "is_factual_product_claim": False})
    profile["important_conflicts"] = []
    for item in result["important_conflicts"]:
        source_ids, _families = relations(item)
        profile["important_conflicts"].append({"summary": str(item["summary"]), "field_names": list(item["field_names"]), "supporting_evidence_ids": list(item["supporting_evidence_ids"]), "supporting_source_ids": source_ids})
    profile["important_unknowns"] = list(result["important_unknowns"])
    if data.get("input_summary", {}).get("media_items_used", 0) == 0:
        profile["visual_positioning"] = []
    # factual_highlights remain the deterministic values from _base_profile.
    return profile


def process_provider_output(data: dict[str, Any], raw_result: object) -> dict[str, Any]:
    """Use one strict provider DTO -> public profile validation path everywhere."""
    schema_details = _provider_schema_error_details(raw_result, data)
    if schema_details:
        schema_errors = list(dict.fromkeys(
            f"schema_validation_error:{detail['section']}" for detail in schema_details
        ))
        raise ProviderProfileError(
            "schema_validation_error",
            "Structured output nie przechodzi schematu providera.",
            {
                "schema_error": ";".join(schema_errors),
                "schema_validation_errors": schema_details,
                "provider_raw_output": raw_result if isinstance(raw_result, dict) else {},
            },
        )

    profile = _profile_from_model_result(data, raw_result)
    final_schema_errors = validate_final_profile_sections_schema({
        key: profile.get(key) for key in product_profile_response_schema()["required"]
    })
    if final_schema_errors:
        raise ProviderProfileError(
            "schema_validation_error",
            "Zmapowany wynik nie przechodzi publicznego schematu profilu.",
            {
                "schema_error": ";".join(final_schema_errors),
                "schema_validation_errors": [
                    {"section": error.removeprefix("schema_validation_error:"), "item_index": None, "loc": [], "type": "public_contract", "message": "Błąd walidacji ProductProfileV1."}
                    for error in final_schema_errors
                ],
                "provider_raw_output": raw_result if isinstance(raw_result, dict) else {},
                "normalized_candidate": profile,
            },
        )

    semantic_errors = validate_profile_against_input(profile, data)
    if semantic_errors:
        raise ProviderProfileError(
            "semantic_validation_error",
            "Wynik providera nie przechodzi walidacji semantycznej.",
            {
                "semantic_error": ";".join(semantic_errors),
                "semantic_validation_errors": semantic_errors,
                "narrative_word_count": len(str(profile.get("narrative_summary", "")).split()),
                "invalid_references": _invalid_reference_details(profile, data),
                "provider_raw_output": raw_result if isinstance(raw_result, dict) else {},
                "normalized_candidate": profile,
            },
        )
    return profile


def _openai_profile(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key: raise ProviderProfileError("provider_configuration_error", "Brak OPENAI_API_KEY.")
    try:
        max_requests = int(os.getenv("PRODUCT_PROFILE_MAX_REQUESTS", "1"))
    except ValueError as exc:
        raise ProviderProfileError("provider_configuration_error", "PRODUCT_PROFILE_MAX_REQUESTS musi być liczbą całkowitą.") from exc
    if max_requests < 1:
        raise ProviderProfileError("provider_configuration_error", "PRODUCT_PROFILE_MAX_REQUESTS blokuje request profilu.")
    body, effective_data, sent_media_ids = build_openai_request(data)
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode("utf-8"), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response: payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ProviderProfileError("provider_incomplete_response", str(exc)) from exc
    result, diagnostic = _extract_structured_output(payload, effective_data)
    try:
        profile = process_provider_output(effective_data, result)
    except ProviderProfileError as exc:
        exc.diagnostic = {**diagnostic, **exc.diagnostic}
        raise
    diagnostic["provider_raw_output"] = result
    diagnostic["media_items_used"] = len(sent_media_ids)
    diagnostic["sent_media_ids"] = sent_media_ids
    profile["generation"].update({"openai_requests_attempted_this_run": 1, "openai_requests_succeeded_this_run": 1, "profile_request_count_total": 1, "cached": False, "generated_at": utc_now(), "semantic_profile_nonempty": True, "profile_quality_valid": True})
    return profile, diagnostic


def _write_diagnostic(product_slug: str, diagnostic: dict[str, Any], *, root: Path = PROFILE_ROOT, parsed: dict[str, Any] | None = None) -> None:
    atomic_write_json(diagnostic_path(product_slug, root), diagnostic)
    if parsed is not None: atomic_write_json(parsed_output_path(product_slug, root), parsed)


def cache_valid(profile: dict[str, Any], data: dict[str, Any]) -> bool:
    generation = profile.get("generation", {}) if isinstance(profile.get("generation"), dict) else {}
    return bool(profile.get("profile_status") == "generated" and generation.get("profile_quality_valid") is True and generation.get("canonical_input_hash") == data["canonical_input_hash"] and generation.get("cache_key") == data["cache_key"] and generation.get("prompt_version") == PRODUCT_PROFILE_PROMPT_VERSION and generation.get("schema_version") == PRODUCT_PROFILE_SCHEMA_VERSION)


def _generation_lock(product_slug: str, profile_root: Path = PROFILE_ROOT) -> FileLock:
    """Share the run coordinator's per-product lock namespace.

    The file name intentionally matches ``RunCoordinator.product_lock_path`` so
    a profile request cannot overlap a research run for the same product.
    """
    return FileLock(profile_root.parent / "run_locks" / f"product-{product_slug}.lock", {"run_id": f"profile:{uuid.uuid4().hex}", "product_slug": product_slug, "scope": "product"})


def _owned_run_lock(product_slug: str, run_id: str, profile_root: Path) -> bool:
    """Allow the pipeline owner through without releasing or replacing its lock."""
    lock_path = profile_root.parent / "run_locks" / f"product-{product_slug}.lock"
    payload = read_json(lock_path, {})
    return isinstance(payload, dict) and str(payload.get("run_id", "")) == run_id and str(payload.get("product_slug", "")) == product_slug


def generate_from_transmission_payload(payload_path: Path, *, expected_hash: str, allow_openai: bool, profile_root: Path = PROFILE_ROOT, provider_call: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> tuple[dict[str, Any], bool, list[str]]:
    payload = read_json(payload_path, {})
    if not isinstance(payload, dict) or _hash(payload) != expected_hash: raise ValueError("Hash payloadu nie zgadza się z jawną zgodą transmisji.")
    data = transmission_profile_input(payload, expected_hash)
    path = profile_path(str(data["product_slug"]), profile_root); existing = read_json(path, {})
    if isinstance(existing, dict) and cache_valid(existing, data):
        cached = deepcopy(existing)
        cached.setdefault("generation", {}).update({"cached": True, "openai_requests_attempted_this_run": 0, "openai_requests_succeeded_this_run": 0})
        return cached, True, []
    if not has_profile_material(data):
        return insufficient_evidence_profile(data), False, []
    if not allow_openai: raise PermissionError("Wymagane jest jawne --allow-openai.")
    lock = _generation_lock(str(data["product_slug"]), profile_root)
    lock.acquire()
    try:
        existing = read_json(path, {})
        if isinstance(existing, dict) and cache_valid(existing, data):
            cached = deepcopy(existing)
            cached.setdefault("generation", {}).update({"cached": True, "openai_requests_attempted_this_run": 0, "openai_requests_succeeded_this_run": 0})
            return cached, True, []
        if provider_call:
            raw_result, diagnostic = provider_call(data)
            try:
                profile = process_provider_output(data, raw_result)
            except ProviderProfileError as exc:
                exc.diagnostic = {**diagnostic, **exc.diagnostic}
                raise
            diagnostic["provider_raw_output"] = raw_result
        else:
            profile, diagnostic = _openai_profile(data)
        previous_total = int(existing.get("generation", {}).get("profile_request_count_total", 0)) if isinstance(existing, dict) and isinstance(existing.get("generation"), dict) else 0
        profile["profile_status"] = "generated"
        profile["generation"].update({"canonical_input_hash": data["canonical_input_hash"], "transmission_payload_hash": expected_hash, "cache_key": data["cache_key"], "model_name": PRODUCT_PROFILE_MODEL, "prompt_version": PRODUCT_PROFILE_PROMPT_VERSION, "schema_version": PRODUCT_PROFILE_SCHEMA_VERSION, "openai_requests_attempted_this_run": 1, "openai_requests_succeeded_this_run": 1, "profile_request_count_total": previous_total + 1, "cached": False, "generated_at": utc_now(), "semantic_profile_nonempty": True, "profile_quality_valid": True})
    except ProviderProfileError as exc:
        diagnostic = {**_response_diagnostic(data), **exc.diagnostic, "parser_error": exc.diagnostic.get("parser_error", exc.code) if exc.diagnostic else exc.code}
        _write_rejected_outputs(
            str(data["product_slug"]),
            exc.diagnostic.get("provider_raw_output") if isinstance(exc.diagnostic.get("provider_raw_output"), dict) else None,
            exc.diagnostic.get("normalized_candidate") if isinstance(exc.diagnostic.get("normalized_candidate"), dict) else None,
            diagnostic,
            data,
            root=profile_root,
        )
        diagnostic.pop("provider_raw_output", None)
        diagnostic.pop("normalized_candidate", None)
        _write_diagnostic(str(data["product_slug"]), diagnostic, root=profile_root)
        failed = _base_profile(data, "failed"); failed["generation"].update({"openai_requests_attempted_this_run": 1, "openai_requests_succeeded_this_run": 0, "profile_request_count_total": 0, "generated_at": utc_now(), "failure_code": exc.code, "failure_reason": str(exc), "transmission_payload_hash": expected_hash})
        # A failure is a separate attempt; never overwrite a valid last result.
        atomic_write_json(attempt_path(str(data["product_slug"]), profile_root), failed)
        return failed, False, [exc.code]
    else:
        raw_result = diagnostic.pop("provider_raw_output", None)
        _write_diagnostic(
            str(data["product_slug"]),
            diagnostic,
            root=profile_root,
            parsed=raw_result if isinstance(raw_result, dict) else None,
        )
        atomic_write_json(path, profile)
        return profile, False, []
    finally:
        lock.release()


def generate_deterministic_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Offline preview only; it is intentionally never a cacheable AI profile."""
    profile = _base_profile(data, "not_generated")
    profile["one_sentence_summary"] = f"{data['brand']} {data['model']}: lokalny podgląd danych do profilu.".strip()
    profile["narrative_summary"] = " ".join(["Lokalny podgląd nie zastępuje odpowiedzi AI."] * 20)
    return profile


def generate_or_load_profile(product_slug: str, *, allow_openai: bool = False, no_openai: bool = False, force: bool = False, max_images: int = 8, profile_root: Path = PROFILE_ROOT, owned_lock_run_id: str | None = None) -> tuple[dict[str, Any], bool]:
    data = build_profile_input(product_slug, max_images=max_images); path = profile_path(product_slug, profile_root); existing = read_json(path, {})
    if isinstance(existing, dict) and cache_valid(existing, data) and not force:
        cached = deepcopy(existing)
        cached.setdefault("generation", {}).update({"cached": True, "openai_requests_attempted_this_run": 0, "openai_requests_succeeded_this_run": 0})
        return cached, True
    if not has_profile_material(data):
        return insufficient_evidence_profile(data), False
    if no_openai: return generate_deterministic_profile(data), False
    if not allow_openai: raise PermissionError("Wymagane jest jawne --allow-openai albo --no-openai.")
    lock = _generation_lock(product_slug, profile_root)
    owns_existing_lock = bool(owned_lock_run_id and _owned_run_lock(product_slug, owned_lock_run_id, profile_root))
    if not owns_existing_lock:
        lock.acquire()
    try:
        existing = read_json(path, {})
        if isinstance(existing, dict) and cache_valid(existing, data) and not force:
            cached = deepcopy(existing)
            cached.setdefault("generation", {}).update({"cached": True, "openai_requests_attempted_this_run": 0, "openai_requests_succeeded_this_run": 0})
            return cached, True
        # Non-transmission live mode has no preflight consent boundary.
        try:
            profile, diagnostic = _openai_profile(data)
        except ProviderProfileError as exc:
            diagnostic = {**_response_diagnostic(data), **exc.diagnostic}
            _write_rejected_outputs(
                product_slug,
                exc.diagnostic.get("provider_raw_output") if isinstance(exc.diagnostic.get("provider_raw_output"), dict) else None,
                exc.diagnostic.get("normalized_candidate") if isinstance(exc.diagnostic.get("normalized_candidate"), dict) else None,
                diagnostic,
                data,
                root=profile_root,
            )
            diagnostic.pop("provider_raw_output", None)
            diagnostic.pop("normalized_candidate", None)
            _write_diagnostic(product_slug, diagnostic, root=profile_root)
            failed = _base_profile(data, "failed"); failed["generation"].update({"openai_requests_attempted_this_run": 1, "openai_requests_succeeded_this_run": 0, "failure_code": exc.code, "failure_reason": str(exc), "generated_at": utc_now()})
            atomic_write_json(attempt_path(product_slug, profile_root), failed)
            return failed, False
        raw_result = diagnostic.pop("provider_raw_output", None)
        _write_diagnostic(
            product_slug,
            diagnostic,
            root=profile_root,
            parsed=raw_result if isinstance(raw_result, dict) else None,
        )
        atomic_write_json(path, profile)
        return profile, False
    finally:
        if not owns_existing_lock:
            lock.release()


def get_profile(product_slug: str, *, profile_root: Path = PROFILE_ROOT) -> dict[str, Any]:
    data = build_profile_input(product_slug); stored = read_json(profile_path(product_slug, profile_root), {})
    attempt = read_json(attempt_path(product_slug, profile_root), {})
    attempt_generation = attempt.get("generation", {}) if isinstance(attempt, dict) and isinstance(attempt.get("generation"), dict) else {}
    attempt_meta = {"latest_generation_attempt_status": str(attempt.get("profile_status", "")), "latest_failure_code": str(attempt_generation.get("failure_code", "")), "latest_failure_reason": str(attempt_generation.get("failure_reason", "")), "latest_attempt_at": str(attempt_generation.get("generated_at", ""))}
    if not isinstance(stored, dict) or not stored:
        result = _base_profile(data, "failed" if attempt_meta["latest_generation_attempt_status"] == "failed" else "not_generated")
        result["generation"].update(attempt_meta)
        return result
    if cache_valid(stored, data):
        result = deepcopy(stored); result.setdefault("generation", {}).update(attempt_meta); return result
    stale = _base_profile(data, "stale")
    stale["generation"].update({"failure_code": "stale_profile", "failure_reason": "Profil utworzono dla wcześniejszego kontraktu wejścia, promptu lub schematu.", **attempt_meta})
    return stale
