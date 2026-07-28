"""Small, dependency-free helpers for passing offer IDs between pipeline stages."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable


class RunCancelledError(RuntimeError):
    """Raised at a pipeline boundary after the durable worker requested cancel."""


def cancellation_requested(path: str | Path | None) -> bool:
    """Read the worker's ephemeral control file; it is never durable state."""
    if not path:
        return False
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(value.get("cancel_requested")) if isinstance(value, dict) else False


def raise_if_cancelled(path: str | Path | None) -> None:
    if cancellation_requested(path):
        raise RunCancelledError("Research anulowany przez użytkownika.")


def normalized_offer_ids(values: Iterable[object]) -> set[str]:
    """Return non-empty offer IDs without changing their string representation."""
    return {str(value).strip() for value in values if str(value or "").strip()}


def load_offer_ids(path: str | Path, keys: tuple[str, ...] = ("fetched_offer_ids", "offer_ids")) -> set[str]:
    """Load IDs from a pipeline context JSON, CSV with offer_id, or a line list."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku z identyfikatorami ofert: {source}")

    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return set()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        for key in keys:
            values = payload.get(key)
            if isinstance(values, list):
                return normalized_offer_ids(values)
        return set()
    if isinstance(payload, list):
        return normalized_offer_ids(payload)

    if source.suffix.lower() == ".csv":
        with source.open(encoding="utf-8", newline="") as handle:
            return normalized_offer_ids(row.get("offer_id", "") for row in csv.DictReader(handle))
    return normalized_offer_ids(line.strip() for line in text.splitlines())
