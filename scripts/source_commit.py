"""Shared post-fetch commit for normalized FIELDNOTE sources.

The function is intentionally source-neutral: an Allegro or manufacturer
adapter hands it a normalized document and deterministic candidates.  It
creates one global source identity, one explicit product relation and only
evidence that survived deterministic validation.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from p0_runtime import atomic_write_json, global_aggregation_lock, utc_now
from provenance_v1 import build_product_provenance, provenance_path
from quality_gate import FIELDS, apply_quality_gate, load_registry
from source_lifecycle import (
    PRODUCT_SOURCE_LINKS_PATH,
    REGISTRY_V1_PATH,
    default_product_source_link,
    default_source_record,
    globalize_source_record,
    read_product_source_links,
    read_source_records,
    write_product_source_links,
    write_source_records,
)


ROOT = Path(__file__).resolve().parent.parent


def read_json(path: Path, fallback: Any) -> Any:
    try:
        import json
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else fallback
    except (OSError, ValueError):
        return fallback


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def _source_record(
    *, source_id: str, source_type: str, brand: str, model: str, original_url: str,
    canonical_url: str, raw_snapshot_path: Path, clean_snapshot_path: Path,
    content_hash: str, content_family_id: str, title: str,
) -> dict[str, Any]:
    base = default_source_record(source_id)
    is_manufacturer = source_type == "manufacturer" or source_type.startswith("manufacturer_")
    base.update({
        "source_type": source_type,
        "marketplace": "manufacturer" if is_manufacturer else "allegro",
        "brand": brand,
        "model": model,
        "original_url": original_url,
        "canonical_url": canonical_url,
        "domain": urlparse(canonical_url).netloc.lower(),
        "first_seen_at": utc_now(),
        "last_seen_at": utc_now(),
    })
    base["fetch"].update({"status": "fetched", "fetched_at": utc_now()})
    base["cleaning"].update({"status": "cleaned", "cleaned_at": utc_now()})
    visual_dir = raw_snapshot_path.parent / "visual"
    visual_snapshot = visual_dir / "visual_snapshot.json"
    visual_blocks = visual_dir / "visual_blocks.jsonl"
    media_manifest = visual_dir / "media_manifest.jsonl"
    visual_metadata = read_json(visual_snapshot, {}) if visual_snapshot.exists() else {}
    base["content"].update({
        "content_hash": content_hash,
        "content_family_id": content_family_id,
        "raw_snapshot_path": relative(raw_snapshot_path),
        "clean_snapshot_path": relative(clean_snapshot_path),
        "snapshot_available": True,
        "visual_snapshot_path": relative(visual_snapshot) if visual_snapshot.exists() else None,
        "visual_blocks_path": relative(visual_blocks) if visual_blocks.exists() else None,
        "media_manifest_path": relative(media_manifest) if media_manifest.exists() else None,
        "visual_capture_status": str(visual_metadata.get("capture_status", "skipped")) if isinstance(visual_metadata, dict) else "skipped",
    })
    base["metadata"].update({"title": title})
    record = globalize_source_record(base)
    record.update({
        "authority_level": "manufacturer" if is_manufacturer else "secondary",
        "updated_at": utc_now(),
    })
    return record


def _candidate_dict(candidate: Any) -> dict[str, str]:
    value = asdict(candidate) if hasattr(candidate, "__dataclass_fields__") else candidate
    return value if isinstance(value, dict) else {}


def _merge_candidates(state: dict[str, Any], candidates: Iterable[Any], *, source_id: str, canonical_url: str) -> int:
    fields = state.setdefault("fields", {})
    accepted = 0
    for raw_candidate in candidates:
        candidate = _candidate_dict(raw_candidate)
        field_name = str(candidate.get("field_candidate", "")).strip()
        value = str(candidate.get("normalized_value") or candidate.get("raw_value") or "").strip()
        excerpt = str(candidate.get("excerpt", "")).strip()[:300]
        if field_name not in FIELDS or not value or not excerpt:
            continue
        # Sources never write commercial marketplace facts. The shared
        # benchmark schema has no price/seller fields, but keep the boundary
        # explicit for future schema changes.
        if field_name.casefold() in {"cena", "sprzedawca", "dostępność", "warunki sprzedaży"}:
            continue
        current = fields.setdefault(field_name, {"value": "X", "status": "open", "confidence": "low", "locked": False, "evidence": []})
        evidence = {
            "source_id": source_id,
            "marketplace": "manufacturer",
            "external_offer_id": "",
            "source_url": canonical_url,
            "value": value,
            "evidence": excerpt,
            "validation_status": "valid",
            "extraction_method": "deterministic",
        }
        existing = current.get("evidence") if isinstance(current.get("evidence"), list) else []
        fingerprint = (source_id, excerpt)
        if any((str(item.get("source_id", "")), str(item.get("evidence", ""))) == fingerprint for item in existing if isinstance(item, dict)):
            continue
        existing.append(evidence)
        current["evidence"] = existing
        if str(current.get("value", "X")) == "X":
            current.update({"value": value, "status": "confirmed", "confidence": "high", "locked": True})
        elif str(current.get("value")) != value:
            current["status"] = "conflicting"
            current["locked"] = False
        accepted += 1
    return accepted


def commit_normalized_source_result(
    *, run_id: str, product_slug: str, source_id: str, source_type: str,
    adapter_id: str, original_url: str, canonical_url: str,
    raw_snapshot_path: Path, clean_snapshot_path: Path, content_hash: str,
    content_family_id: str, normalized_document: Any, evidence_candidates: Iterable[Any],
) -> dict[str, int]:
    """Commit a validated source and all product-facing lifecycle artifacts.

    All records are prepared before writes. P0 atomic writers preserve the
    last valid version of every artifact; the product lock prevents concurrent
    commits for the same model.
    """
    group_dir = ROOT / "output" / "model_groups" / product_slug
    group_path = group_dir / "group.json"
    state_path = group_dir / "model_state.json"
    group = read_json(group_path, {})
    state = read_json(state_path, {})
    if not group or not state:
        raise ValueError("Brak group.json lub model_state.json dla produktu.")
    if str(group.get("group_key", "")) != str(state.get("group_key", "")):
        raise ValueError("Niespójny group_key produktu.")
    if not raw_snapshot_path.is_file() or not clean_snapshot_path.is_file():
        raise ValueError("Brak wymaganego raw lub clean snapshotu.")

    record = _source_record(
        source_id=source_id, source_type=source_type, brand=str(group.get("brand", "")),
        model=str(group.get("model", "")), original_url=original_url,
        canonical_url=canonical_url, raw_snapshot_path=raw_snapshot_path,
        clean_snapshot_path=clean_snapshot_path, content_hash=content_hash,
        content_family_id=content_family_id, title=str(getattr(normalized_document, "title", "")),
    )
    record.setdefault("metadata", {})["manufacturer_source_type"] = str(
        getattr(normalized_document, "source_type", "manufacturer_product_page")
    )
    link = default_product_source_link(product_slug, source_id)
    link.update({"group_key": str(group.get("group_key", "")), "product_id": group.get("product_id")})
    link["selection"].update({"selected": True, "role": "manufacturer", "selected_in_run_id": run_id, "selected_at": utc_now(), "selection_reason": adapter_id})
    link["assignment"].update({"status": "assigned", "assigned_at": utc_now(), "assignment_reason": "validated_normalized_document"})
    link["run_ids"] = [run_id]

    staged_state = {**state, "fields": {key: dict(value) for key, value in (state.get("fields", {}) if isinstance(state.get("fields"), dict) else {}).items()}}
    candidates = list(evidence_candidates)
    accepted = _merge_candidates(staged_state, candidates, source_id=source_id, canonical_url=canonical_url)

    lock_root = ROOT / "output" / "locks"
    with global_aggregation_lock(lock_root, run_id):
        sources = {str(item.get("source_id", "")): item for item in read_source_records(REGISTRY_V1_PATH)}
        sources[source_id] = record
        links = {str(item.get("link_id", "")): item for item in read_product_source_links(PRODUCT_SOURCE_LINKS_PATH)}
        prior_link = links.get(link["link_id"])
        if isinstance(prior_link, dict):
            prior_runs = prior_link.get("run_ids") if isinstance(prior_link.get("run_ids"), list) else []
            link["run_ids"] = list(dict.fromkeys([*prior_runs, run_id]))
        links[link["link_id"]] = link
        # Validate/commit identity and relation before producing provenance.
        write_source_records(list(sources.values()), REGISTRY_V1_PATH)
        write_product_source_links(list(links.values()), path=PRODUCT_SOURCE_LINKS_PATH, source_ids=set(sources))
        registry = load_registry()
        gated_state, report = apply_quality_gate(staged_state, group, registry)
        atomic_write_json(state_path, gated_state)
        provenance = build_product_provenance(product_slug, group, gated_state)
        atomic_write_json(provenance_path(product_slug), provenance)
        evidence_count = sum(len(item.get("evidence_v1", [])) for item in provenance.get("fields", {}).values() if isinstance(item, dict))
        manufacturer_evidence = sum(
            1 for item in provenance.get("fields", {}).values() if isinstance(item, dict)
            for evidence in item.get("evidence_v1", []) if isinstance(evidence, dict) and evidence.get("source_id") == source_id
        )
        link["usage"].update({
            "used_in_final_product": manufacturer_evidence > 0,
            "used_fields_count": manufacturer_evidence,
            "confirmed_fields_count": manufacturer_evidence,
            "conflicting_fields_count": 0,
            "rejected_evidence_count": int(report.get("fields_rejected", 0) or 0),
        })
        links[link["link_id"]] = link
        write_product_source_links(list(links.values()), path=PRODUCT_SOURCE_LINKS_PATH, source_ids=set(sources))
    return {"evidence_candidates_accepted": accepted, "evidence_records_created": manufacturer_evidence, "quality_rejections": int(report.get("fields_rejected", 0) or 0)}
