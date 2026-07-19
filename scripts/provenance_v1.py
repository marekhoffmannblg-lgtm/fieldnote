"""Offline EvidenceItemV1 normalization and product-quality metrics for FIELDNOTE."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quality_gate import FIELDS, normalize_value
from source_lifecycle import read_product_source_links, read_source_records


ROOT = Path(__file__).resolve().parent.parent
PROVENANCE_ROOT = ROOT / "output" / "provenance_v1"
VALIDATION_TO_STATUS = {
    "valid": "valid",
    "weak": "weak",
    "conflicting": "conflicting",
    "rejected": "rejected",
    "unattributed_legacy": "unattributed_legacy",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.lower()).strip()


def evidence_id(product_slug: str, field_name: str, source_id: str, excerpt: str, index: int) -> str:
    basis = "|".join((product_slug, field_name, source_id, normalized_text(excerpt), str(index)))
    return "evidence:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def normalize_legacy_evidence(raw: object, current_value: object) -> list[dict[str, str]]:
    """Handle historic string/dict/list/null shapes without guessing source IDs."""
    entries = raw if isinstance(raw, list) else [raw]
    normalized: list[dict[str, str]] = []
    for item in entries:
        if isinstance(item, str) and item.strip():
            normalized.append({"source_id": "", "value": str(current_value or "").strip(), "excerpt": item.strip(), "validation_status": ""})
        elif isinstance(item, dict):
            excerpt = str(item.get("evidence", item.get("excerpt", "")) or "").strip()
            if excerpt:
                normalized.append({
                    "source_id": str(item.get("source_id", "") or "").strip(),
                    "value": str(item.get("value", current_value) or current_value or "").strip(),
                    "excerpt": excerpt,
                    "validation_status": str(item.get("validation_status", "") or "").strip(),
                })
    return normalized


def source_authority(source: dict[str, Any]) -> tuple[str, float]:
    source_type = str(source.get("source_type", "") or "")
    marketplace = str(source.get("marketplace", "") or "")
    if source_type == "manufacturer" or marketplace == "manufacturer":
        return "primary", 1.0
    if source_type == "marketplace_offer":
        return "marketplace", 0.7
    return "other", 0.4


def source_content_family(source: dict[str, Any]) -> str:
    content = source.get("content", {}) if isinstance(source.get("content"), dict) else {}
    family = str(content.get("content_family_id") or source.get("content_family_id") or "").strip()
    if family:
        return family
    content_hash = str(content.get("content_hash") or source.get("content_hash") or "").strip()
    if content_hash:
        return f"hash:{content_hash}"
    return f"source:{source.get('source_id', '')}"


def source_metadata(source: dict[str, Any]) -> tuple[str, float]:
    metadata = source.get("metadata", {}) if isinstance(source.get("metadata"), dict) else {}
    fetched_at = str(source.get("last_seen_at") or source.get("first_seen_at") or source.get("fetched_at") or "")
    score = metadata.get("offer_quality_score", source.get("quality_score", 0))
    try:
        return fetched_at, float(score or 0)
    except (TypeError, ValueError):
        return fetched_at, 0.0


def evidence_sort_key(item: dict[str, Any]) -> tuple[int, float, str, float, str]:
    # Validity, authority, earlier persisted capture, quality and stable ID.
    status_rank = {"valid": 0, "weak": 1, "conflicting": 2, "rejected": 3, "unattributed_legacy": 4}.get(str(item.get("evidence_status")), 5)
    fetched_at = str(item.get("fetched_at") or "9999-12-31T23:59:59Z")
    return (status_rank, -float(item.get("confirmation_weight", 0) or 0), fetched_at, -float(item.get("source_quality", 0) or 0), str(item.get("source_id") or ""))


def build_evidence_item(
    *,
    product_slug: str,
    field_name: str,
    current_value: str,
    raw: dict[str, str],
    index: int,
    source_by_id: dict[str, dict[str, Any]],
    link_by_source: dict[str, dict[str, Any]],
    field_validation: str,
) -> dict[str, Any]:
    source_id = raw["source_id"]
    source = source_by_id.get(source_id, {})
    link = link_by_source.get(source_id, {})
    validation = raw["validation_status"] or field_validation
    if not source_id:
        evidence_status = "unattributed_legacy"
        validation = "unattributed_legacy"
        authority, authority_weight = "unknown", 0.0
        family = None
        source_quality = 0.0
        fetched_at = ""
        link_id = None
    elif not source or not link:
        evidence_status = "rejected"
        validation = "invalid_reference"
        authority, authority_weight = "unknown", 0.0
        family = None
        source_quality = 0.0
        fetched_at = ""
        link_id = None
    else:
        evidence_status = VALIDATION_TO_STATUS.get(validation, "weak" if current_value != "X" else "rejected")
        authority, authority_weight = source_authority(source)
        family = source_content_family(source)
        fetched_at, source_quality = source_metadata(source)
        link_id = str(link.get("link_id") or "") or None
    confidence = "high" if evidence_status == "valid" else "medium" if evidence_status in {"weak", "conflicting"} else "low" if evidence_status == "rejected" else "unknown"
    return {
        "schema_version": "1",
        "evidence_id": evidence_id(product_slug, field_name, source_id, raw["excerpt"], index),
        "product_slug": product_slug,
        "field_name": field_name,
        "normalized_field_name": normalize_value(field_name),
        "value": raw["value"] or current_value or None,
        "normalized_value": normalize_value(raw["value"] or current_value) or None,
        "source_id": source_id or None,
        "product_source_link_id": link_id,
        "excerpt": raw["excerpt"][:300],
        "evidence_status": evidence_status,
        "validation_status": validation,
        "confidence": confidence,
        "content_family_id": family,
        "is_independent_confirmation": False,
        "source_authority": authority,
        "confirmation_weight": authority_weight if evidence_status in {"valid", "weak"} else 0.0,
        "source_quality": source_quality,
        "fetched_at": fetched_at,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def aggregate_field(items: list[dict[str, Any]], final_value: str) -> dict[str, Any]:
    eligible = [item for item in items if item["evidence_status"] in {"valid", "weak"}]
    eligible.sort(key=evidence_sort_key)
    families: set[str] = set()
    primary: dict[str, Any] | None = None
    confirming: list[str] = []
    conflicting: list[str] = []
    rejected: list[str] = []
    for item in items:
        status = str(item["evidence_status"])
        if status == "rejected":
            rejected.append(item["evidence_id"])
        elif status == "conflicting":
            conflicting.append(item["evidence_id"])
    for item in eligible:
        family = str(item.get("content_family_id") or "")
        if not primary:
            primary = item
            item["is_independent_confirmation"] = True
            if family:
                families.add(family)
            continue
        if family and family not in families:
            item["is_independent_confirmation"] = True
            families.add(family)
        else:
            item["is_independent_confirmation"] = False
        confirming.append(item["evidence_id"])
    valid_values = {str(item.get("normalized_value") or "") for item in eligible if item.get("is_independent_confirmation")}
    has_conflict = len({value for value in valid_values if value}) > 1
    return {
        "primary_evidence_id": primary.get("evidence_id") if primary else None,
        "confirming_evidence_ids": confirming,
        "conflicting_evidence_ids": conflicting,
        "rejected_evidence_ids": rejected,
        "independent_confirmations_count": sum(bool(item.get("is_independent_confirmation")) for item in eligible),
        "total_sources_count": len({str(item.get("source_id")) for item in items if item.get("source_id")}),
        "content_families_count": len(families),
        "has_conflict": has_conflict,
        "final_value": final_value,
    }


def product_metrics(fields: dict[str, dict[str, Any]], aggregates: dict[str, dict[str, Any]], analysis_complete: bool) -> dict[str, Any]:
    if not analysis_complete:
        return {"coverage_percent": None, "evidence_quality_percent": None, "source_confidence_percent": None, "high_confidence_fields": 0, "weak_fields": 0, "conflicting_fields": 0, "unattributed_legacy_fields": 0, "missing_fields": None, "fields_missing": None, "analysis_complete": False, "fields_total": len(FIELDS), "fields_present": 0, "fields_valid": 0, "fields_weak": 0, "fields_conflicting": 0, "fields_rejected": 0, "fields_unattributed": 0}
    total = len(FIELDS)
    present = valid = weak = conflicting = unattributed = rejected = 0
    high = 0
    primary_weights: list[float] = []
    for name in FIELDS:
        field = fields.get(name, {})
        aggregate = aggregates.get(name, {})
        value = str(field.get("value", "X") or "X")
        primary_status = str(field.get("validation_status", ""))
        if value != "X" and primary_status in {"valid", "weak"}:
            present += 1
        if primary_status == "valid" and aggregate.get("primary_evidence_id"):
            valid += 1
        if primary_status == "weak":
            weak += 1
        if primary_status == "rejected":
            rejected += 1
        if field.get("status") == "conflicting" or aggregate.get("has_conflict"):
            conflicting += 1
        if any(item.get("evidence_status") == "unattributed_legacy" for item in field.get("evidence_v1", [])):
            unattributed += 1
        if str(field.get("confidence", "")) == "high" and primary_status == "valid":
            high += 1
        primary_id = str(aggregate.get("primary_evidence_id") or "")
        for item in field.get("evidence_v1", []) if isinstance(field.get("evidence_v1"), list) else []:
            if isinstance(item, dict) and str(item.get("evidence_id") or "") == primary_id:
                try:
                    primary_weights.append(float(item.get("confirmation_weight", 0) or 0))
                except (TypeError, ValueError):
                    pass
                break
    return {
        "coverage_percent": round((present / total) * 100, 2) if total else None,
        "evidence_quality_percent": round((valid / total) * 100, 2) if total else None,
        "source_confidence_percent": round((sum(primary_weights) / len(primary_weights)) * 100, 2) if primary_weights else 0.0,
        "high_confidence_fields": high,
        "weak_fields": weak,
        "conflicting_fields": conflicting,
        "unattributed_legacy_fields": unattributed,
        "missing_fields": total - present,
        "fields_missing": total - present,
        "analysis_complete": True,
        "fields_total": total,
        "fields_present": present,
        "fields_valid": valid,
        "fields_weak": weak,
        "fields_conflicting": conflicting,
        "fields_rejected": rejected,
        "fields_unattributed": unattributed,
    }


def build_product_provenance(product_slug: str, group: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    group_sources = {
        str(item.get("source_id")): item
        for item in group.get("sources", []) if isinstance(item, dict) and item.get("source_id")
    }
    # Group metadata contains persisted content-family decisions made during
    # grouping. It enriches the global identity but never creates a new one.
    source_by_id = {
        str(item.get("source_id")): {**group_sources.get(str(item.get("source_id")), {}), **item}
        for item in read_source_records()
    }
    link_by_source = {str(item.get("source_id")): item for item in read_product_source_links() if item.get("product_slug") == product_slug}
    raw_fields = state.get("fields", {}) if isinstance(state.get("fields"), dict) else {}
    fields: dict[str, dict[str, Any]] = {}
    aggregates: dict[str, dict[str, Any]] = {}
    for field_name in FIELDS:
        raw_field = raw_fields.get(field_name, {})
        field = raw_field if isinstance(raw_field, dict) else {}
        current_value = str(field.get("value", "X") or "X")
        raw_evidence = normalize_legacy_evidence(field.get("evidence"), current_value)
        # evidence_quality carries P1's per-item validation when available.
        quality_evidence = normalize_legacy_evidence(field.get("evidence_quality"), current_value)
        quality_by_fingerprint = {(item["source_id"], normalized_text(item["excerpt"])): item for item in quality_evidence}
        items: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_evidence):
            quality = quality_by_fingerprint.get((raw["source_id"], normalized_text(raw["excerpt"])))
            if quality and quality.get("validation_status"):
                raw = {**raw, "validation_status": quality["validation_status"]}
            items.append(build_evidence_item(
                product_slug=product_slug, field_name=field_name, current_value=current_value, raw=raw, index=index,
                source_by_id=source_by_id, link_by_source=link_by_source,
                field_validation=str(field.get("validation_status", "") or ""),
            ))
        aggregate = aggregate_field(items, current_value)
        fields[field_name] = {"value": current_value, "status": str(field.get("status", "open") or "open"), "confidence": str(field.get("confidence", "low") or "low"), "validation_status": str(field.get("validation_status", "") or ""), "evidence_v1": items, "aggregate": aggregate}
        aggregates[field_name] = aggregate
    metrics = product_metrics(fields, aggregates, bool(raw_fields))
    return {"schema_version": "1", "product_slug": product_slug, "group_key": str(group.get("group_key", "")), "generated_at": utc_now(), "fields": fields, "metrics": metrics}


def provenance_path(product_slug: str) -> Path:
    return PROVENANCE_ROOT / f"{product_slug}.json"


def load_product_provenance(product_slug: str) -> dict[str, Any]:
    return read_json(provenance_path(product_slug), {})
