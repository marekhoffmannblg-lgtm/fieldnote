"""Export a read-only frontend snapshot from the benchmark pipeline outputs.

This script never alters pipeline data.  It creates static JSON files consumed
by the FIELDNOTE frontend so the product catalogue can work without a backend.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from benchmark_taxonomy import is_benchmark_eligible
from catalog_registry import ensure_catalog_product, product_for_group_key
from p0_runtime import atomic_write_json
from provenance_v1 import load_product_provenance
from source_lifecycle import product_source_counters, read_product_source_links, read_source_records


ROOT = Path(__file__).resolve().parent.parent
GROUPS_ROOT = ROOT / "output" / "model_groups"
COVERAGE_PATH = ROOT / "output" / "model_coverage.csv"
BENCHMARK_PATH = ROOT / "output" / "model_benchmark.csv"
REGISTRY_PATH = ROOT / "output" / "source_registry.jsonl"
ANALYSIS_STATUS_PATH = ROOT / "output" / "product_analysis_status.json"
PRODUCT_STATE_PATH = ROOT / "output" / "product_state.json"
FRONTEND_DATA = ROOT / "fieldnote-frontend" / "src" / "data" / "generated"
PRODUCTS_DIR = FRONTEND_DATA / "products"


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def atomic_write(path: Path, value: object) -> None:
    atomic_write_json(path, value)


def as_bool(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def public_status_from_state(state: dict[str, Any], valid_final_result: bool) -> str:
    active = str(state.get("active_run_status", "none"))
    if active in {"queued", "running"}:
        return "analysis_running"
    if valid_final_result or state.get("result_status") == "ready":
        return "refresh_recommended" if as_bool(state.get("refresh_recommended")) else "ready"
    if state.get("last_failed_run_id"):
        return "analysis_failed"
    return "refresh_recommended"


def as_number(value: object) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def short_excerpt(value: object, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalized_text(value: object) -> str:
    """Normalize local text only for deterministic evidence-to-snapshot matching."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def local_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def source_snapshot_paths(source: dict[str, Any]) -> tuple[str, str]:
    """Return existing raw and clean snapshot paths without touching local files."""
    lifecycle_content = source.get("content", {}) if isinstance(source.get("content"), dict) else {}
    direct_raw = str(lifecycle_content.get("raw_snapshot_path", "") or "")
    direct_clean = str(lifecycle_content.get("clean_snapshot_path", "") or "")
    if direct_raw or direct_clean:
        return direct_raw, direct_clean
    content_path = Path(str(source.get("content_path", "") or ""))
    manufacturer_root = Path(str(source.get("manufacturer_source_path", "") or ""))
    if content_path and not content_path.is_absolute():
        content_path = ROOT / content_path
    if manufacturer_root and not manufacturer_root.is_absolute():
        manufacturer_root = ROOT / manufacturer_root

    clean_candidates = [content_path] if str(content_path) not in {"", "."} else []
    raw_candidates: list[Path] = []
    if clean_candidates:
        raw_candidates.append(content_path.parent / "markdown.md")
    if str(manufacturer_root) not in {"", "."}:
        raw_candidates.append(manufacturer_root / "markdown.md")
        clean_candidates.append(manufacturer_root / "technical_clean.md")
    offer_sections = Path(str(source.get("offer_sections_path", "") or ""))
    if str(offer_sections) not in {"", "."}:
        if not offer_sections.is_absolute():
            offer_sections = ROOT / offer_sections
        raw_candidates.append(offer_sections.parent / "markdown.md")
        clean_candidates.append(offer_sections.parent / "technical_clean.md")

    raw = next((candidate for candidate in raw_candidates if candidate.is_file()), None)
    clean = next((candidate for candidate in clean_candidates if candidate.is_file()), None)
    return (local_path(raw) if raw else "", local_path(clean) if clean else "")


def source_details(source_id: str, source: dict[str, Any], supplied_url: str = "") -> dict[str, str]:
    registry_exists = bool(source_id and source)
    original_url = str(source.get("original_url") or source.get("source_url") or supplied_url or "").strip()
    source_url = str(source.get("canonical_url") or original_url or "").strip()
    raw_snapshot_path, clean_snapshot_path = source_snapshot_paths(source) if source else ("", "")
    if not source_id:
        source_status = "unchecked"
    elif registry_exists and original_url and (raw_snapshot_path or clean_snapshot_path):
        source_status = "active"
    else:
        source_status = "unavailable"
    return {
        "source_id": source_id,
        "marketplace": str(source.get("marketplace", "")).strip(),
        "source_type": str(source.get("source_type", "")).strip(),
        "source_url": source_url,
        "original_url": original_url,
        "offer_id": str(source.get("external_offer_id") or source.get("offer_id") or "").strip(),
        "domain": str(source.get("domain") or urlparse(source_url).netloc.lower()).strip(),
        "fetched_at": str(source.get("fetched_at", "")).strip(),
        "raw_snapshot_path": raw_snapshot_path,
        "clean_snapshot_path": clean_snapshot_path,
        "content_hash": str(source.get("content_hash", "")).strip(),
        "source_status": source_status,
    }


def matched_local_source(excerpt: str, sources: dict[str, dict[str, Any]], source_order: list[str]) -> str:
    """Find an exact textual witness for legacy string-only evidence.

    A source is attached only after the complete normalized evidence is present
    in a local immutable snapshot. This avoids inventing provenance for a
    field that happened to have no structured source id in older state files.
    """
    needle = normalized_text(excerpt)
    if not needle:
        return ""
    for source_id in source_order:
        source = sources.get(source_id, {})
        raw_path, clean_path = source_snapshot_paths(source)
        for relative_path in (clean_path, raw_path):
            if not relative_path:
                continue
            path = ROOT / relative_path
            try:
                if needle in normalized_text(path.read_text(encoding="utf-8")):
                    return source_id
            except OSError:
                continue
    return ""


def load_coverage() -> dict[str, dict[str, str]]:
    if not COVERAGE_PATH.exists():
        return {}
    with COVERAGE_PATH.open(encoding="utf-8", newline="") as handle:
        return {
            row.get("group_key", ""): row
            for row in csv.DictReader(handle)
            if row.get("group_key", "")
        }


def load_benchmark_group_keys() -> set[str]:
    """Return only groups with a persisted, openable benchmark row."""
    if not BENCHMARK_PATH.exists():
        return set()
    with BENCHMARK_PATH.open(encoding="utf-8", newline="") as handle:
        return {str(row.get("group_key", "")).strip() for row in csv.DictReader(handle) if row.get("group_key")}


def load_registry() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if REGISTRY_PATH.exists():
        for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("source_id"):
                records[str(record["source_id"])] = record
    # V2 is the global source catalogue. It enriches (and supersedes) sparse
    # legacy entries without creating a product relation.
    for record in read_source_records():
        source_id = str(record.get("source_id", ""))
        if source_id:
            records[source_id] = {**records.get(source_id, {}), **record}
    return records


def normalized_evidence_v1(items: object, sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "")
        details = source_details(source_id, sources.get(source_id, {}))
        result.append({
            **details,
            "evidence_id": str(item.get("evidence_id") or ""),
            "product_source_link_id": item.get("product_source_link_id"),
            "value": str(item.get("value") or ""),
            "excerpt": short_excerpt(item.get("excerpt", "")),
            "evidence": str(item.get("excerpt") or ""),
            "evidence_status": str(item.get("evidence_status") or ""),
            "validation_status": str(item.get("validation_status") or ""),
            "confidence": str(item.get("confidence") or "unknown"),
            "content_family_id": item.get("content_family_id"),
            "is_independent_confirmation": bool(item.get("is_independent_confirmation")),
            "source_authority": str(item.get("source_authority") or "unknown"),
            "confirmation_weight": item.get("confirmation_weight", 0),
        })
    return result


def normalized_evidence(
    raw: object,
    field: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    source_order: list[str],
) -> list[dict[str, str]]:
    if raw is None or raw == "":
        return []
    entries = raw if isinstance(raw, list) else [raw]
    evidence: list[dict[str, str]] = []
    for entry in entries:
        if isinstance(entry, dict):
            excerpt = str(entry.get("evidence", "")).strip()
            source_id = str(entry.get("source_id", "")).strip()
            source_value = str(entry.get("value", field.get("value", ""))).strip()
            source_url = str(entry.get("source_url", "")).strip()
            source_type = str(entry.get("source_type", "")).strip()
        elif isinstance(entry, str):
            excerpt = entry.strip()
            source_id = matched_local_source(excerpt, sources, source_order)
            source_value = str(field.get("value", "")).strip()
            source_url = ""
            source_type = ""
        else:
            continue
        if not excerpt:
            continue
        source = sources.get(source_id, {})
        details = source_details(source_id, source, source_url)
        source_url = details["source_url"]
        source_type = source_type or details["source_type"]
        evidence.append(
            {
                **details,
                "source_type": source_type,
                "source_url": source_url,
                "value": source_value,
                "excerpt": short_excerpt(excerpt),
                "evidence": excerpt,
            }
        )
    return evidence


def export_product(group_path: Path, coverage: dict[str, str], registry: dict[str, dict[str, Any]], product_states: dict[str, Any], benchmark_groups: set[str]) -> tuple[dict[str, Any], dict[str, Any], int, int]:
    group = read_json(group_path)
    state_path = group_path.parent / "model_state.json"
    state = read_json(state_path) if state_path.exists() else {}
    group_key = str(group.get("group_key", ""))
    brand = str(group.get("brand", "")).strip()
    model = str(group.get("model", "")).strip()
    catalog_product = product_for_group_key(group_key) or ensure_catalog_product(brand, model)
    slug = group_path.parent.name
    fields = state.get("fields", {}) if isinstance(state.get("fields"), dict) else {}
    provenance = load_product_provenance(slug)
    provenance_fields = provenance.get("fields", {}) if isinstance(provenance.get("fields"), dict) else {}
    group_sources = [source for source in group.get("sources", []) if isinstance(source, dict) and source.get("source_id")]
    source_order = [str(source["source_id"]) for source in group_sources]
    sources = dict(registry)
    for source in group_sources:
        source_id = str(source["source_id"])
        # Registry enriches sparse group sources with immutable capture metadata.
        sources[source_id] = {**source, **registry.get(source_id, {})}

    # ProductSourceLink is the only product-to-source relation.  A global
    # SourceRecord is a catalogue entry and must never inflate product counts.
    product_links = [
        link
        for link in read_product_source_links()
        if str(link.get("product_slug", "")) == slug
    ]
    source_counts = product_source_counters(product_links, sources)

    details_fields: list[dict[str, Any]] = []
    fields_with_evidence = 0
    fields_without_evidence = 0
    for field_name, raw_field in fields.items():
        field = raw_field if isinstance(raw_field, dict) else {}
        provenance_field = provenance_fields.get(field_name, {}) if isinstance(provenance_fields.get(field_name), dict) else {}
        evidence = normalized_evidence_v1(provenance_field.get("evidence_v1"), sources) or normalized_evidence(field.get("evidence"), field, sources, source_order)
        if evidence:
            fields_with_evidence += 1
        else:
            fields_without_evidence += 1
        first = evidence[0] if evidence else {}
        details_fields.append(
            {
                "field_name": str(field_name),
                "value": str(field.get("value", "X") or "X"),
                "status": str(field.get("status", "open") or "open"),
                "confidence": str(field.get("confidence", "low") or "low"),
                "locked": as_bool(field.get("locked")),
                "validation_status": str(field.get("validation_status", "rejected") or "rejected"),
                "quality": field.get("quality", {}) if isinstance(field.get("quality"), dict) else {},
                "provenance": provenance_field.get("aggregate", {}) if isinstance(provenance_field.get("aggregate"), dict) else {},
                "evidence": evidence,
                "source_id": first.get("source_id", ""),
                "source_type": first.get("source_type", ""),
                "source_url": first.get("source_url", ""),
                "original_url": first.get("original_url", ""),
                "offer_id": first.get("offer_id", ""),
                "domain": first.get("domain", ""),
                "fetched_at": first.get("fetched_at", ""),
                "raw_snapshot_path": first.get("raw_snapshot_path", ""),
                "clean_snapshot_path": first.get("clean_snapshot_path", ""),
                "content_hash": first.get("content_hash", ""),
                "source_status": first.get("source_status", "unchecked"),
                "excerpt": first.get("excerpt", ""),
            }
        )

    lifecycle = product_states.get(slug, {}) if isinstance(product_states, dict) else {}
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    # A valid final result has priority over a later failed refresh/reanalysis.
    # The failure remains visible in History but must not hide usable product data.
    taxonomy_eligible = is_benchmark_eligible(group)
    valid_final_result = bool(details_fields) and bool(coverage) and group_key in benchmark_groups and taxonomy_eligible
    status = public_status_from_state(lifecycle, valid_final_result)
    # The coverage report may count a conflicting field in more than one
    # bucket. The state file is the canonical field inventory for the UI.
    fields_total = len(details_fields) or (
        int(coverage.get("fields_confirmed", 0) or 0) + int(coverage.get("fields_open", 0) or 0)
    )
    metrics = provenance.get("metrics", {}) if isinstance(provenance.get("metrics"), dict) else {}
    analysis_complete = bool(metrics.get("analysis_complete")) if metrics else bool(fields)
    fields_completed = int(metrics.get("fields_present", coverage.get("fields_confirmed", 0)) or 0)
    missing_fields_count = metrics.get("missing_fields") if analysis_complete else None
    if missing_fields_count is not None:
        missing_fields_count = int(missing_fields_count)
    conflicts_count = sum(item["status"] == "conflicting" for item in details_fields)
    coverage_value = metrics.get("coverage_percent") if analysis_complete and metrics else as_number(coverage.get("coverage_percent"))
    updated_at = datetime.fromtimestamp(group_path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
    catalog_item = {
        "brand": brand,
        "model": model,
        "slug": slug,
        "product_id": str(catalog_product.get("product_id", "")),
        "category": str(catalog_product.get("category", "")),
        "category_slug": str(catalog_product.get("category_slug", "")),
        "subcategory": str(catalog_product.get("subcategory", group.get("subcategory", ""))),
        "benchmark_category": str(catalog_product.get("benchmark_category", group.get("benchmark_category", ""))),
        "taxonomy_version": str(catalog_product.get("taxonomy_version", group.get("taxonomy_version", ""))),
        "taxonomy_status": str(catalog_product.get("taxonomy_status", group.get("taxonomy_status", "review_required"))),
        "status": status,
        "status_reason": str(lifecycle.get("refresh_reason") or lifecycle.get("error") or ("Wymaga klasyfikacji benchmarkowej." if not taxonomy_eligible else "")),
        "status_updated_at": str(lifecycle.get("updated_at") or updated_at),
        "coverage": coverage_value,
        "fields_total": fields_total,
        "fields_completed": fields_completed,
        # Compatibility field: its meaning is deliberately "used in final
        # product", not "all technical/global records".
        "sources_count": int(source_counts["used_count"]),
        "source_counts": source_counts,
        "missing_fields_count": missing_fields_count,
        "conflicts_count": conflicts_count,
        "metrics": metrics,
        "updated_at": updated_at,
        "marketplaces": sorted(str(value) for value in group.get("marketplaces", []) if value),
    }
    product = {
        **catalog_item,
        "group_key": group_key,
        "source_counts": source_counts,
        "sources": [
            {
                **source_details(str(source.get("source_id", "")), sources.get(str(source.get("source_id", "")), source)),
            }
            for source in group_sources
        ],
        "fields": details_fields,
    }
    return catalog_item, product, fields_with_evidence, fields_without_evidence


def main() -> int:
    coverage = load_coverage()
    benchmark_groups = load_benchmark_group_keys()
    registry = load_registry()
    product_states = read_json(PRODUCT_STATE_PATH)
    if not isinstance(product_states, dict):
        product_states = read_json(ANALYSIS_STATUS_PATH)
    if not GROUPS_ROOT.exists():
        print(f"Brak katalogu grup: {GROUPS_ROOT}")
        return 1
    catalog: list[dict[str, Any]] = []
    state_count = waiting_count = evidence_count = without_evidence_count = 0
    for group_path in sorted(GROUPS_ROOT.glob("*/group.json")):
        group = read_json(group_path)
        group_key = str(group.get("group_key", ""))
        if not group_key:
            continue
        catalog_item, product, with_evidence, without_evidence = export_product(group_path, coverage.get(group_key, {}), registry, product_states, benchmark_groups)
        catalog.append(catalog_item)
        atomic_write(PRODUCTS_DIR / f"{catalog_item['slug']}.json", product)
        evidence_count += with_evidence
        without_evidence_count += without_evidence
        if catalog_item["status"] == "ready":
            state_count += 1
        elif catalog_item["status"] in {"analysis_running", "analysis_failed", "refresh_recommended"}:
            waiting_count += 1
    catalog.sort(key=lambda item: (str(item["brand"]).lower(), str(item["model"]).lower()))
    atomic_write(FRONTEND_DATA / "catalog.json", catalog)
    print(f"groups_exported={len(catalog)}")
    print(f"products_with_state={state_count}")
    print(f"products_waiting={waiting_count}")
    print(f"fields_with_evidence={evidence_count}")
    print(f"fields_without_evidence={without_evidence_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
