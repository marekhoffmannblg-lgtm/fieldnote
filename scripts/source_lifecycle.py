"""Canonical SourceRecordV1 lifecycle registry for offline FIELDNOTE data."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from p0_runtime import atomic_write_json, atomic_write_text


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_V1_PATH = PROJECT_ROOT / "output" / "source_registry_v1.jsonl"
PRODUCT_SOURCE_LINKS_PATH = PROJECT_ROOT / "output" / "product_source_links_v1.jsonl"
SOURCE_TYPES = {"marketplace_offer", "manufacturer", "other"}
ROLES = {"primary", "supplementary", "manufacturer", "unknown"}
FETCH_STATUSES = {"not_requested", "queued", "fetched", "failed", "skipped", "unavailable"}
CLEANING_STATUSES = {"not_started", "cleaned", "failed", "skipped"}
ASSIGNMENT_STATUSES = {"unassigned", "assigned", "rejected", "duplicate"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def default_source_record(source_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1", "source_id": source_id, "source_type": "other", "marketplace": None, "offer_id": None,
        "product_id": None, "product_slug": None, "group_key": None, "brand": None, "model": None,
        "original_url": None, "canonical_url": None, "domain": None,
        "selection": {"selected": False, "role": "unknown", "selected_at": None, "selected_in_run_id": None, "selection_rank": None, "selection_reason": None},
        "fetch": {"status": "not_requested", "requested_at": None, "fetched_at": None, "http_status": None, "error": None},
        "cleaning": {"status": "not_started", "cleaned_at": None, "error": None},
        "assignment": {"status": "unassigned", "assigned_at": None, "assignment_reason": None, "rejection_reason": None, "duplicate_of": None},
        "usage": {"used_in_final_product": False, "used_fields_count": 0, "confirmed_fields_count": 0, "conflicting_fields_count": 0, "rejected_evidence_count": 0},
        "content": {"content_hash": None, "content_family_id": None, "raw_snapshot_path": None, "clean_snapshot_path": None, "snapshot_available": False,
                    "visual_snapshot_path": None, "visual_blocks_path": None, "media_manifest_path": None, "visual_capture_status": "skipped"},
        "metadata": {"title": None, "price_amount": None, "price_currency": None, "seller_name": None, "seller_rating": None, "offer_quality_score": None},
        "first_seen_at": None, "last_seen_at": None, "updated_at": utc_now(),
    }


def default_product_source_link(product_slug: str, source_id: str) -> dict[str, Any]:
    """Product-specific lifecycle. A link never creates a second source identity."""
    return {
        "schema_version": "1",
        "link_id": f"{product_slug}|{source_id}",
        "product_slug": product_slug,
        "group_key": "",
        "product_id": None,
        "source_id": source_id,
        "selection": {
            "selected": False,
            "role": "unknown",
            "selected_at": None,
            "selected_in_run_id": None,
            "selection_rank": None,
            "selection_reason": None,
        },
        "assignment": {
            "status": "unassigned",
            "assigned_at": None,
            "assignment_reason": None,
            "rejection_reason": None,
            "duplicate_of": None,
        },
        "usage": {
            "used_in_final_product": False,
            "used_fields_count": 0,
            "confirmed_fields_count": 0,
            "conflicting_fields_count": 0,
            "rejected_evidence_count": 0,
        },
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def globalize_source_record(record: dict[str, Any]) -> dict[str, Any]:
    """Drop product relation fields while retaining one durable source identity."""
    global_record = default_source_record(str(record.get("source_id", "")))
    for key in ("source_type", "marketplace", "offer_id", "original_url", "canonical_url", "domain", "fetch", "cleaning", "content", "metadata", "first_seen_at", "last_seen_at", "updated_at"):
        if key in record:
            global_record[key] = record[key]
    global_record["schema_version"] = "2"
    # Brand/model are observations from the source, not a product assignment.
    global_record["observed_brand"] = record.get("brand")
    global_record["observed_model"] = record.get("model")
    global_record.pop("product_id", None)
    global_record.pop("product_slug", None)
    global_record.pop("group_key", None)
    global_record.pop("selection", None)
    global_record.pop("assignment", None)
    global_record.pop("usage", None)
    return global_record


def _run_manifests(project_root: Path) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in (project_root / "output" / "runs").glob("*/manifest.json"):
        value = read_json(path, {})
        if isinstance(value, dict):
            manifests.append(value)
    return manifests


def build_product_source_links(records: Iterable[dict[str, Any]], project_root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    """Build only explicit product relations from group.json or selected run context.

    Queue rows alone deliberately do not create a ProductSourceLink. This is
    what prevents a global candidate offer from silently becoming product data.
    """
    sources_by_id = {str(item.get("source_id", "")): item for item in records if str(item.get("source_id", ""))}
    groups: dict[str, tuple[Path, dict[str, Any]]] = {}
    links: dict[str, dict[str, Any]] = {}
    for path in (project_root / "output" / "model_groups").glob("*/group.json"):
        group = read_json(path, {})
        if not isinstance(group, dict) or not str(group.get("group_key", "")):
            continue
        group_dir = path.parent
        groups[group_dir.name] = (group_dir, group)
        usage = _evidence_usage(group_dir)
        for source in group.get("sources", []) if isinstance(group.get("sources"), list) else []:
            if not isinstance(source, dict):
                continue
            source_id = str(source.get("source_id", "")).strip()
            if source_id not in sources_by_id:
                continue
            link = default_product_source_link(group_dir.name, source_id)
            link.update({"group_key": str(group.get("group_key", "")), "product_id": group.get("product_id")})
            source_usage = usage.get(source_id, {})
            role = "manufacturer" if sources_by_id[source_id].get("source_type") == "manufacturer" else ("primary" if source_usage.get("used") else "supplementary")
            link["selection"].update({"selected": True, "role": role, "selection_reason": "present_in_group_json"})
            link["assignment"].update({"status": "assigned", "assignment_reason": "present_in_group_json"})
            link["usage"].update({
                "used_in_final_product": bool(source_usage.get("used")),
                "used_fields_count": int(source_usage.get("used", 0)),
                "confirmed_fields_count": int(source_usage.get("confirmed", 0)),
                "conflicting_fields_count": int(source_usage.get("conflicting", 0)),
                "rejected_evidence_count": int(source_usage.get("rejected", 0)),
            })
            links[link["link_id"]] = link
    for manifest in _run_manifests(project_root):
        product_slug = str(manifest.get("product_slug", "")).strip()
        if product_slug not in groups:
            continue
        selected_offer_ids = manifest.get("selected_offer_ids")
        if not isinstance(selected_offer_ids, list):
            continue
        group_dir, group = groups[product_slug]
        for offer_id in selected_offer_ids:
            source_id = f"allegro:{str(offer_id).strip()}"
            if source_id not in sources_by_id:
                continue
            link_id = f"{product_slug}|{source_id}"
            link = links.get(link_id) or default_product_source_link(product_slug, source_id)
            link.update({"group_key": str(group.get("group_key", "")), "product_id": group.get("product_id")})
            link["selection"].update({
                "selected": True,
                "selected_in_run_id": str(manifest.get("run_id", "")) or None,
                "selected_at": manifest.get("created_at") or manifest.get("started_at"),
                "selection_reason": "explicit_selected_offer_id_in_run_manifest",
            })
            if link["assignment"]["status"] != "assigned":
                link["assignment"].update({"status": "unassigned", "assignment_reason": "selected_in_run_not_present_in_group_json"})
            links[link_id] = link
    return sorted(links.values(), key=lambda item: (item["product_slug"], item["source_id"]))


def _relative(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return None


def _snapshot_paths(source: dict[str, Any], queue: dict[str, str]) -> tuple[str | None, str | None]:
    output_dir = str(queue.get("output_dir", "") or "").strip()
    candidates: list[Path] = []
    for key in ("content_path", "manufacturer_source_path"):
        value = str(source.get(key, "") or "").strip()
        if value:
            candidates.append(PROJECT_ROOT / value)
    if output_dir:
        candidates.append(PROJECT_ROOT / output_dir / "markdown.md")
    raw = next((path for path in candidates if path.name == "markdown.md" and path.exists()), None)
    clean_candidates = [PROJECT_ROOT / str(source.get("content_path", "") or "")] if source.get("content_path") else []
    if output_dir:
        clean_candidates.append(PROJECT_ROOT / output_dir / "technical_clean.md")
    clean = next((path for path in clean_candidates if path.exists()), None)
    return _relative(raw), _relative(clean)


def _evidence_usage(group_dir: Path) -> dict[str, dict[str, int]]:
    state = read_json(group_dir / "model_state.json", {})
    result: dict[str, dict[str, int]] = {}
    fields = state.get("fields", {}) if isinstance(state, dict) else {}
    if not isinstance(fields, dict):
        return result
    for item in fields.values():
        if not isinstance(item, dict):
            continue
        final_value = str(item.get("value", "X") or "X")
        evidence = item.get("evidence")
        sequence = evidence if isinstance(evidence, list) else [evidence]
        for raw in sequence:
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("source_id", "") or "").strip()
            if not source_id:
                continue
            bucket = result.setdefault(source_id, {"used": 0, "confirmed": 0, "conflicting": 0, "rejected": 0})
            evidence_value = str(raw.get("value", final_value) or final_value)
            if final_value != "X" and evidence_value.casefold() == final_value.casefold():
                bucket["used"] += 1
                bucket["confirmed"] += 1
            else:
                bucket["conflicting"] += 1
        rejected = item.get("rejected_evidence")
        sequence = rejected if isinstance(rejected, list) else [rejected]
        for raw in sequence:
            if isinstance(raw, dict) and str(raw.get("source_id", "") or "").strip():
                bucket = result.setdefault(str(raw["source_id"]), {"used": 0, "confirmed": 0, "conflicting": 0, "rejected": 0})
                bucket["rejected"] += 1
    return result


def _queue_rows() -> dict[str, dict[str, str]]:
    path = PROJECT_ROOT / "output" / "firecrawl_offer_queue.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {str(row.get("offer_id", "")).strip(): row for row in csv.DictReader(handle) if str(row.get("offer_id", "")).strip()}


def build_source_records(project_root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    """Infer lifecycle only where local data is explicit; never fetch or guess."""
    global PROJECT_ROOT
    original_root = PROJECT_ROOT
    PROJECT_ROOT = project_root
    try:
        legacy = read_jsonl(project_root / "output" / "source_registry.jsonl")
        queue = _queue_rows()
        groups: dict[str, tuple[Path, dict[str, Any]]] = {}
        for path in (project_root / "output" / "model_groups").glob("*/group.json"):
            group = read_json(path, {})
            if isinstance(group, dict) and str(group.get("group_key", "")):
                groups[str(group["group_key"])] = (path.parent, group)
        group_sources: dict[str, dict[str, Any]] = {}
        groups_by_key = {key: value for key, value in groups.items()}
        usage: dict[str, dict[str, int]] = {}
        for group_dir, group in groups.values():
            for source in group.get("sources", []) if isinstance(group.get("sources"), list) else []:
                if isinstance(source, dict) and str(source.get("source_id", "")):
                    group_sources[str(source["source_id"])] = {"group": group, "source": source, "group_dir": group_dir}
            usage.update(_evidence_usage(group_dir))
        records: dict[str, dict[str, Any]] = {}
        for legacy_source in legacy:
            source_id = str(legacy_source.get("source_id", "") or "").strip()
            if not source_id:
                continue
            offer_id = str(legacy_source.get("external_offer_id") or legacy_source.get("offer_id") or "").strip() or None
            queue_row = queue.get(offer_id or "", {})
            assignment_info = group_sources.get(source_id)
            legacy_group_key = str(legacy_source.get("group_key", "") or "")
            inferred_group = groups_by_key.get(legacy_group_key)
            group = assignment_info.get("group", {}) if assignment_info else {}
            group_source = assignment_info.get("source", {}) if assignment_info else {}
            group_dir = assignment_info.get("group_dir") if assignment_info else None
            record = default_source_record(source_id)
            legacy_type = str(legacy_source.get("source_type") or "other")
            source_type = "manufacturer" if legacy_type.startswith("manufacturer") else legacy_type if legacy_type in SOURCE_TYPES else "other"
            record.update({
                "source_type": source_type, "marketplace": legacy_source.get("marketplace"),
                "offer_id": offer_id, "product_id": legacy_source.get("product_id"),
                "product_slug": group_dir.name if isinstance(group_dir, Path) else (inferred_group[0].name if inferred_group else None),
                "group_key": group.get("group_key") or legacy_group_key, "brand": group.get("brand") or legacy_source.get("brand"),
                "model": group.get("model") or legacy_source.get("model"), "original_url": legacy_source.get("source_url") or legacy_source.get("canonical_url"),
                "canonical_url": legacy_source.get("canonical_url") or legacy_source.get("source_url"),
            })
            record["domain"] = legacy_source.get("domain") or (urlparse(str(record["canonical_url"] or "")).netloc or None)
            selected = bool(queue_row) or bool(assignment_info)
            role = "manufacturer" if record["source_type"] == "manufacturer" or record["marketplace"] == "manufacturer" else ("primary" if source_id in usage else "supplementary" if assignment_info else "unknown")
            record["selection"].update({"selected": selected, "role": role, "selected_at": queue_row.get("last_attempt_at") or legacy_source.get("fetched_at") or None, "selection_reason": "present_in_queue_or_group" if selected else "legacy_registry_without_selection_record"})
            queue_status = str(queue_row.get("status", "") or "").lower()
            raw, clean = _snapshot_paths(legacy_source, queue_row)
            fetch_status = "failed" if queue_status == "error" else "fetched" if queue_status == "fetched" or raw or clean else "not_requested"
            record["fetch"].update({"status": fetch_status, "requested_at": queue_row.get("last_attempt_at") or None, "fetched_at": queue_row.get("fetched_at") or legacy_source.get("fetched_at") or None, "error": queue_row.get("error_message") or None})
            record["cleaning"].update({"status": "cleaned" if clean else "not_started" if raw else "skipped", "cleaned_at": legacy_source.get("fetched_at") if clean else None})
            if assignment_info:
                record["assignment"].update({"status": "assigned", "assigned_at": legacy_source.get("fetched_at") or None, "assignment_reason": "present_in_group_json"})
            else:
                record["assignment"].update({"status": "unassigned", "assignment_reason": "not_present_in_model_group"})
            use = usage.get(source_id, {})
            record["usage"].update({"used_in_final_product": bool(use.get("used")), "used_fields_count": int(use.get("used", 0)), "confirmed_fields_count": int(use.get("confirmed", 0)), "conflicting_fields_count": int(use.get("conflicting", 0)), "rejected_evidence_count": int(use.get("rejected", 0))})
            record["content"].update({"content_hash": legacy_source.get("content_hash") or None, "content_family_id": legacy_source.get("content_family_id") or None, "raw_snapshot_path": raw, "clean_snapshot_path": clean, "snapshot_available": bool(raw or clean)})
            record["metadata"].update({"title": legacy_source.get("title") or None, "price_amount": legacy_source.get("price") or None, "seller_name": legacy_source.get("seller_name") or None, "seller_rating": legacy_source.get("seller_rating") or None, "offer_quality_score": legacy_source.get("quality_score")})
            record["first_seen_at"] = legacy_source.get("fetched_at") or queue_row.get("last_attempt_at") or None
            record["last_seen_at"] = queue_row.get("last_attempt_at") or legacy_source.get("fetched_at") or None
            records[source_id] = record
        # Queue-only rows, especially failed selected offers, must remain visible.
        for offer_id, row in queue.items():
            source_id = f"allegro:{offer_id}"
            if source_id in records:
                continue
            brand = str(row.get("brand") or "").strip()
            model = str(row.get("detected_model") or "").strip()
            queue_group_key = f"{brand.casefold()}|{model.casefold()}" if brand and model else ""
            queue_group = groups_by_key.get(queue_group_key)
            record = default_source_record(source_id)
            record.update({"source_type": "marketplace_offer", "marketplace": "allegro", "offer_id": offer_id, "product_slug": queue_group[0].name if queue_group else None, "group_key": queue_group_key or None, "brand": brand or None, "model": model or None, "original_url": row.get("normalized_url") or None, "canonical_url": row.get("normalized_url") or None, "domain": urlparse(row.get("normalized_url") or "").netloc or None})
            record["selection"].update({"selected": True, "role": "unknown", "selected_at": row.get("last_attempt_at") or None, "selection_reason": "present_in_firecrawl_queue"})
            queue_status = str(row.get("status", "") or "").lower()
            record["fetch"].update({"status": "failed" if queue_status == "error" else "fetched" if queue_status == "fetched" else "queued", "requested_at": row.get("last_attempt_at") or None, "fetched_at": row.get("fetched_at") or None, "error": row.get("error_message") or None})
            record["assignment"].update({"status": "unassigned", "assignment_reason": "selected_offer_not_present_in_model_group"})
            output_dir = project_root / str(row.get("output_dir") or "")
            raw = _relative(output_dir / "markdown.md") if (output_dir / "markdown.md").exists() else None
            clean = _relative(output_dir / "technical_clean.md") if (output_dir / "technical_clean.md").exists() else None
            record["content"].update({"raw_snapshot_path": raw, "clean_snapshot_path": clean, "snapshot_available": bool(raw or clean)})
            records[source_id] = record
        validate_source_records(records.values(), project_root=project_root)
        return sorted(records.values(), key=lambda item: item["source_id"])
    finally:
        PROJECT_ROOT = original_root


def validate_source_record(record: dict[str, Any], *, known_source_ids: set[str] | None = None, project_root: Path = PROJECT_ROOT) -> None:
    if not str(record.get("source_id", "")).strip():
        raise ValueError("source_id jest wymagane")
    if record.get("source_type") not in SOURCE_TYPES:
        raise ValueError("Nieprawidłowy source_type")
    # SourceRecordV2 is deliberately global. Product selection, assignment and
    # benchmark usage belong exclusively to ProductSourceLink.
    if str(record.get("schema_version", "")) == "2":
        for forbidden in ("product_id", "product_slug", "group_key", "selection", "assignment", "usage"):
            if forbidden in record:
                raise ValueError("Globalny SourceRecord nie może zawierać relacji produktowej")
        fetch = record.get("fetch")
        cleaning = record.get("cleaning")
        if not isinstance(fetch, dict) or not isinstance(cleaning, dict):
            raise ValueError("Brak statusu pobrania lub cleanera")
        if fetch.get("status") not in FETCH_STATUSES or cleaning.get("status") not in CLEANING_STATUSES:
            raise ValueError("Nieprawidłowy status globalnego źródła")
        return
    selection, fetch, cleaning, assignment = (record.get(key) for key in ("selection", "fetch", "cleaning", "assignment"))
    if not all(isinstance(item, dict) for item in (selection, fetch, cleaning, assignment)):
        raise ValueError("Brak części lifecycle")
    if selection.get("role") not in ROLES or fetch.get("status") not in FETCH_STATUSES or cleaning.get("status") not in CLEANING_STATUSES or assignment.get("status") not in ASSIGNMENT_STATUSES:
        raise ValueError("Nieprawidłowy status lifecycle")
    if assignment.get("status") == "rejected" and not str(assignment.get("rejection_reason") or "").strip():
        raise ValueError("Odrzucone źródło wymaga rejection_reason")
    if assignment.get("status") == "unassigned" and not str(assignment.get("assignment_reason") or "").strip():
        raise ValueError("Nieprzypisane źródło wymaga assignment_reason")
    if assignment.get("status") == "duplicate":
        duplicate_of = str(assignment.get("duplicate_of") or "").strip()
        if not duplicate_of or (known_source_ids is not None and duplicate_of not in known_source_ids):
            raise ValueError("Duplikat musi wskazywać istniejące duplicate_of")
    group_key, product_slug = str(record.get("group_key") or ""), str(record.get("product_slug") or "")
    if group_key and product_slug and "|" in group_key:
        brand, model = group_key.split("|", 1)
        expected = f"{brand.replace(' ', '-')}__{model.replace(' ', '-')}"
        if product_slug != expected:
            raise ValueError("product_slug nie jest zgodny z group_key")
    for key in ("raw_snapshot_path", "clean_snapshot_path"):
        value = record.get("content", {}).get(key) if isinstance(record.get("content"), dict) else None
        if value:
            resolved = (project_root / str(value)).resolve()
            try:
                resolved.relative_to(project_root.resolve())
            except ValueError as exc:
                raise ValueError("Snapshot musi znajdować się pod PROJECT_ROOT") from exc


def validate_source_records(records: Iterable[dict[str, Any]], *, project_root: Path = PROJECT_ROOT) -> None:
    values = list(records)
    ids = [str(item.get("source_id", "")) for item in values]
    if len(ids) != len(set(ids)):
        raise ValueError("source_id musi być unikalne")
    known = set(ids)
    for record in values:
        validate_source_record(record, known_source_ids=known, project_root=project_root)


def validate_lifecycle_transition(previous: dict[str, Any], current: dict[str, Any]) -> None:
    """Reject lifecycle regressions that would erase durable source history."""
    fetch_allowed = {
        "not_requested": {"not_requested", "queued", "fetched", "skipped", "unavailable"},
        "queued": {"queued", "fetched", "failed", "skipped", "unavailable"},
        "fetched": {"fetched", "unavailable"},
        "failed": {"failed", "queued", "fetched", "unavailable"},
        "skipped": {"skipped", "queued", "fetched", "unavailable"},
        "unavailable": {"unavailable", "queued", "fetched"},
    }
    cleaning_allowed = {
        "not_started": {"not_started", "cleaned", "failed", "skipped"},
        "cleaned": {"cleaned"}, "failed": {"failed", "not_started", "cleaned"}, "skipped": {"skipped", "not_started", "cleaned"},
    }
    assignment_allowed = {
        "unassigned": {"unassigned", "assigned", "rejected", "duplicate"},
        "assigned": {"assigned", "duplicate"}, "rejected": {"rejected"}, "duplicate": {"duplicate", "assigned"},
    }
    for section, allowed in (("fetch", fetch_allowed), ("cleaning", cleaning_allowed), ("assignment", assignment_allowed)):
        before = str(previous.get(section, {}).get("status", ""))
        after = str(current.get(section, {}).get("status", ""))
        if before in allowed and after not in allowed[before]:
            raise ValueError(f"Nieprawidłowe przejście {section}: {before} -> {after}")


def write_source_records(records: Iterable[dict[str, Any],], path: Path = REGISTRY_V1_PATH) -> None:
    values = list(records)
    validate_source_records(values, project_root=path.parent.parent)
    previous = {str(item.get("source_id")): item for item in read_jsonl(path)}
    for value in values:
        old = previous.get(str(value.get("source_id")))
        if isinstance(old, dict) and str(old.get("schema_version", "")) != "2" and str(value.get("schema_version", "")) != "2":
            validate_lifecycle_transition(old, value)
    text = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in values)
    atomic_write_text(path, text)


def read_source_records(path: Path = REGISTRY_V1_PATH) -> list[dict[str, Any]]:
    return read_jsonl(path)


def validate_product_source_link(
    link: dict[str, Any],
    *,
    known_source_ids: set[str] | None = None,
) -> None:
    product_slug = str(link.get("product_slug", "")).strip()
    source_id = str(link.get("source_id", "")).strip()
    if not product_slug or not source_id:
        raise ValueError("ProductSourceLink wymaga product_slug i source_id")
    if str(link.get("link_id", "")) != f"{product_slug}|{source_id}":
        raise ValueError("link_id musi być stabilnym kluczem product_slug|source_id")
    if known_source_ids is not None and source_id not in known_source_ids:
        raise ValueError("ProductSourceLink wskazuje nieznane globalne źródło")
    selection = link.get("selection")
    assignment = link.get("assignment")
    usage = link.get("usage")
    if not all(isinstance(item, dict) for item in (selection, assignment, usage)):
        raise ValueError("ProductSourceLink ma niepełny lifecycle")
    if selection.get("role") not in ROLES or assignment.get("status") not in ASSIGNMENT_STATUSES:
        raise ValueError("Nieprawidłowy status ProductSourceLink")
    if assignment.get("status") == "unassigned" and not str(assignment.get("assignment_reason") or "").strip():
        raise ValueError("Nieprzypisany ProductSourceLink wymaga powodu")


def validate_product_source_links(
    links: Iterable[dict[str, Any]],
    *,
    source_ids: set[str] | None = None,
) -> None:
    values = list(links)
    link_ids = [str(item.get("link_id", "")) for item in values]
    if len(link_ids) != len(set(link_ids)):
        raise ValueError("link_id musi być unikalne")
    for link in values:
        validate_product_source_link(link, known_source_ids=source_ids)


def read_product_source_links(path: Path = PRODUCT_SOURCE_LINKS_PATH) -> list[dict[str, Any]]:
    return read_jsonl(path)


def write_product_source_links(
    links: Iterable[dict[str, Any]],
    *,
    path: Path = PRODUCT_SOURCE_LINKS_PATH,
    source_ids: set[str] | None = None,
) -> None:
    values = list(links)
    validate_product_source_links(values, source_ids=source_ids)
    text = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in values)
    atomic_write_text(path, text)


def source_counters(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    values = list(records)
    return {
        "selected_count": sum(bool(item.get("selection", {}).get("selected")) for item in values),
        "fetched_count": sum(item.get("fetch", {}).get("status") == "fetched" for item in values),
        "fetch_failed_count": sum(item.get("fetch", {}).get("status") == "failed" for item in values),
        "cleaned_count": sum(item.get("cleaning", {}).get("status") == "cleaned" for item in values),
        "assigned_count": sum(item.get("assignment", {}).get("status") == "assigned" for item in values),
        "unattached_count": sum(item.get("fetch", {}).get("status") == "fetched" and item.get("assignment", {}).get("status") == "unassigned" for item in values),
        "used_count": sum(bool(item.get("usage", {}).get("used_in_final_product")) for item in values),
        "rejected_count": sum(item.get("assignment", {}).get("status") == "rejected" for item in values),
        "duplicate_count": sum(item.get("assignment", {}).get("status") == "duplicate" for item in values),
        "unavailable_count": sum(item.get("fetch", {}).get("status") == "unavailable" for item in values),
    }


def product_source_counters(
    links: Iterable[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Count a product's lifecycle from links, never from global candidates."""
    values = list(links)

    def fetch_status(link: dict[str, Any]) -> str:
        source = sources_by_id.get(str(link.get("source_id", "")), {})
        fetch = source.get("fetch", {}) if isinstance(source.get("fetch"), dict) else {}
        return str(fetch.get("status", ""))

    def cleaning_status(link: dict[str, Any]) -> str:
        source = sources_by_id.get(str(link.get("source_id", "")), {})
        cleaning = source.get("cleaning", {}) if isinstance(source.get("cleaning"), dict) else {}
        return str(cleaning.get("status", ""))

    selected = [item for item in values if bool((item.get("selection") or {}).get("selected"))]
    # Marketplace lifecycle counters remain stable when a primary manufacturer
    # source is attached. Manufacturer sources are reported separately rather
    # than changing the historical Allegro selection/fetch totals.
    marketplace_selected = [
        item for item in selected
        if str((sources_by_id.get(str(item.get("source_id", "")), {}) or {}).get("marketplace", "")) != "manufacturer"
    ]
    manufacturer_selected = [item for item in selected if item not in marketplace_selected]
    return {
        "selected_count": len(marketplace_selected),
        "fetched_count": sum(fetch_status(item) == "fetched" for item in marketplace_selected),
        "fetch_failed_count": sum(fetch_status(item) == "failed" for item in marketplace_selected),
        "cleaned_count": sum(cleaning_status(item) == "cleaned" for item in marketplace_selected),
        "assigned_count": sum((item.get("assignment") or {}).get("status") == "assigned" for item in marketplace_selected),
        "unattached_count": sum(fetch_status(item) == "fetched" and (item.get("assignment") or {}).get("status") == "unassigned" for item in marketplace_selected),
        "used_count": sum(bool((item.get("usage") or {}).get("used_in_final_product")) for item in marketplace_selected),
        "rejected_count": sum((item.get("assignment") or {}).get("status") == "rejected" for item in marketplace_selected),
        "duplicate_count": sum((item.get("assignment") or {}).get("status") == "duplicate" for item in marketplace_selected),
        "unavailable_count": sum(fetch_status(item) == "unavailable" for item in marketplace_selected),
        "manufacturer_selected_count": len(manufacturer_selected),
        "manufacturer_fetched_count": sum(fetch_status(item) == "fetched" for item in manufacturer_selected),
        "manufacturer_assigned_count": sum((item.get("assignment") or {}).get("status") == "assigned" for item in manufacturer_selected),
    }
