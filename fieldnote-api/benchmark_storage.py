"""Minimal file storage for competitive benchmark relationships."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from p0_runtime import atomic_write_json


BENCHMARK_ID_PATTERN = re.compile(r"^benchmark_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class BenchmarkValidationError(ValueError):
    """A business rule prevents saving a benchmark relationship."""


class BenchmarkNotFoundError(FileNotFoundError):
    """The requested benchmark manifest does not exist."""


class BenchmarkConflictError(FileExistsError):
    """A generated benchmark identifier is already occupied."""


def semantic_benchmark_payload(group_key: str, profile: str, participants: list[dict[str, Any]], price_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a stable snapshot envelope; price is explicitly a separate dimension."""
    return {
        "schema_version": "strollers.v1",
        "benchmark_group_key": str(group_key).strip(),
        "profile": str(profile).strip(),
        "participants": participants,
        "price_summary": dict(price_summary or {}),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalized_brand(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def normalized_configuration(value: object) -> str:
    raw = " ".join(str(value or "").split()).casefold()
    compact = raw.replace(" ", "").replace("-", "")
    return {"2in1": "2w1", "2w1": "2w1", "3in1": "3w1", "3w1": "3w1", "4in1": "4w1", "4w1": "4w1"}.get(compact, raw)


def manifest_path(root: Path, benchmark_id: str) -> Path:
    if not BENCHMARK_ID_PATTERN.fullmatch(str(benchmark_id)):
        raise BenchmarkNotFoundError("Nie znaleziono benchmarku.")
    return root / benchmark_id / "manifest.json"


def read_manifest(root: Path, benchmark_id: str) -> dict[str, Any]:
    path = manifest_path(root, benchmark_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkNotFoundError("Nie znaleziono benchmarku.") from exc
    if not isinstance(value, dict):
        raise BenchmarkNotFoundError("Nie znaleziono benchmarku.")
    return value


def _product_index(products: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(product.get("product_id", "")).strip(): product for product in products if str(product.get("product_id", "")).strip()}


def validate_relationship(payload: dict[str, Any], products: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if str(payload.get("benchmark_type", "competitive")) != "competitive":
        raise BenchmarkValidationError("Obsługiwany jest wyłącznie benchmark typu competitive.")
    index = _product_index(products)
    anchor_id = str(payload.get("anchor_product_id", "")).strip()
    anchor = index.get(anchor_id)
    if anchor is None:
        raise BenchmarkValidationError(f"Nie istnieje produkt anchor: {anchor_id or '[pusty]'}." )
    if normalized_brand(anchor.get("brand")) != "lionelo":
        raise BenchmarkValidationError(f"Anchor {anchor_id} musi być produktem marki Lionelo.")
    anchor_group = str(anchor.get("benchmark_group", "")).strip()
    if not anchor_group:
        raise BenchmarkValidationError(f"Anchor {anchor_id} nie ma przypisanej grupy benchmarkowej.")
    requested_group = str(payload.get("benchmark_group_key", "")).strip()
    if requested_group != anchor_group:
        raise BenchmarkValidationError(f"benchmark_group_key musi być równy grupie anchora: {anchor_group}.")
    anchor_configuration = normalized_configuration(anchor.get("configuration", anchor.get("stroller_configuration", "")))
    requested_configuration = normalized_configuration(payload.get("configuration", anchor_configuration))
    if requested_configuration != anchor_configuration:
        raise BenchmarkValidationError(f"configuration musi być zgodne z anchorem: {anchor_configuration or '[brak]'}.")

    participant_ids = [str(value).strip() for value in payload.get("participant_product_ids", [])]
    if not participant_ids:
        raise BenchmarkValidationError("Benchmark konkurencyjny wymaga co najmniej jednego uczestnika.")
    if len(participant_ids) != len(set(participant_ids)):
        raise BenchmarkValidationError("Lista uczestników zawiera zduplikowany product_id.")
    if anchor_id in participant_ids:
        raise BenchmarkValidationError("Anchor nie może być uczestnikiem benchmarku.")

    participants: list[dict[str, Any]] = []
    for product_id in participant_ids:
        participant = index.get(product_id)
        if participant is None:
            raise BenchmarkValidationError(f"Nie istnieje uczestnik benchmarku: {product_id}.")
        if normalized_brand(participant.get("brand")) == "lionelo":
            raise BenchmarkValidationError(f"Uczestnik {product_id} nie może być produktem marki Lionelo.")
        group = str(participant.get("benchmark_group", "")).strip()
        if not group:
            raise BenchmarkValidationError(f"Uczestnik {product_id} nie ma przypisanej grupy benchmarkowej.")
        if group != anchor_group:
            raise BenchmarkValidationError(f"Uczestnik {product_id} należy do grupy {group}, a anchor do {anchor_group}.")
        participant_configuration = normalized_configuration(participant.get("configuration", participant.get("stroller_configuration", "")))
        if participant_configuration != anchor_configuration:
            raise BenchmarkValidationError(f"Uczestnik {product_id} ma konfigurację {participant_configuration or '[brak]'}, a anchor {anchor_configuration or '[brak]'}.")
        participants.append(participant)
    return anchor, participants


def create_manifest(root: Path, payload: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
    anchor, _participants = validate_relationship(payload, products)
    anchor_configuration = normalized_configuration(anchor.get("configuration", anchor.get("stroller_configuration", "")))
    benchmark_id = f"benchmark_{uuid.uuid4()}"
    path = manifest_path(root, benchmark_id)
    if path.exists():
        raise BenchmarkConflictError(f"Benchmark {benchmark_id} już istnieje.")
    timestamp = utc_now()
    manifest = {
        "benchmark_id": benchmark_id,
        "benchmark_type": "competitive",
        "benchmark_group_key": str(anchor.get("benchmark_group", "")).strip(),
        "configuration": anchor_configuration,
        "anchor_product_id": str(anchor.get("product_id", "")).strip(),
        "participant_product_ids": [str(value).strip() for value in payload["participant_product_ids"]],
        "title": str(payload.get("title", "")).strip(),
        "status": str(payload.get("status", "draft")),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    atomic_write_json(path, manifest)
    return manifest


def list_manifests(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("benchmark_*/manifest.json")) if root.exists() else []:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or str(value.get("benchmark_type")) != "competitive":
            continue
        records.append(value)
    return sorted(records, key=lambda item: str(item.get("updated_at", "")), reverse=True)


def product_summary(product: dict[str, Any]) -> dict[str, str]:
    return {
        "product_id": str(product.get("product_id", "")),
        "brand": str(product.get("brand", "")),
        "model": str(product.get("model", "")),
        "configuration": str(product.get("configuration", "") or ""),
        "benchmark_group": str(product.get("benchmark_group", "") or ""),
    }
