from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_FIELDS = (
    "Marka", "Model", "Status", "Rama", "Koła", "Udźwig", "Regulacja oparcia",
    "Auto-folding", "Składanie jedną ręką", "Waga", "Wymiary po złożeniu",
    "Siedzisko", "Amortyzacja", "Koła 360°", "Hamulec", "Budka XXL",
    "Filtr UPF50+", "Wodoodporna budka", "Regulacja rączki",
    "Wymiary oparcia / miejsce do spania", "Akcesoria",
)
CRITICAL_FIELDS = {"Rama", "Koła", "Udźwig", "Waga", "Wymiary po złożeniu", "Amortyzacja", "Hamulec", "Budka XXL", "Regulacja rączki"}


def data_root() -> Path:
    configured = os.getenv("BENCHMARK_DATA_ROOT", "").strip()
    return Path(configured).expanduser().resolve() if configured else PROJECT_ROOT


def number(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def integer(value: object) -> int:
    return int(number(value))


def plural(value: object, one: str, few: str, many: str) -> str:
    count = integer(value)
    word = many if 11 <= count % 100 <= 14 else one if count % 10 == 1 else few if count % 10 in {2, 3, 4} else many
    return f"{count} {word}"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def parse_datetime(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_evidence(value: object, current_value: str = "") -> list[dict[str, str]]:
    if value in (None, "", []):
        return []
    items: list[dict[str, str]] = []

    def add(item: object) -> None:
        if isinstance(item, list):
            for child in item:
                add(child)
        elif isinstance(item, dict):
            items.append({key: str(item.get(key, "") or "") for key in ("source_id", "marketplace", "external_offer_id", "source_url", "value", "evidence")})
        elif isinstance(item, str) and item.strip():
            items.append({"source_id": "", "marketplace": "", "external_offer_id": "", "source_url": "", "value": current_value, "evidence": item.strip()})

    add(value)
    return items


def status_label(status: object, value: object = "") -> str:
    if str(value or "") == "X" or str(status or "") == "X":
        return "Brak danych"
    return {"confirmed": "Potwierdzone", "conflicting": "Sprzeczne źródła", "open": "Wymaga sprawdzenia", "unclear": "Niejednoznaczne", "not_found": "Brak potwierdzenia"}.get(str(status or ""), "Wymaga sprawdzenia")


def catalog_status_label(status: object) -> str:
    return {"ready": "Gotowy benchmark", "analyzed_no_coverage": "Analiza bez raportu", "waiting_for_analysis": "Czeka na analizę", "no_sources": "Brak źródeł", "error": "Wymaga sprawdzenia"}.get(str(status or ""), "Nieznany stan")


def run_status_label(status: object) -> str:
    return {"preview": "Podgląd ofert", "success": "Sukces", "partial": "Częściowy sukces", "failed": "Błąd", "running": "W toku"}.get(str(status or ""), "Nieznany")


def model_name(model: dict[str, Any]) -> str:
    return f"{model.get('brand', '')} {model.get('model', '')}".strip()


def slug_for_model(brand: str, model: str) -> str:
    return f"{brand.strip().lower().replace(' ', '-')}--{model.strip().lower().replace(' ', '-')}"


def safe_query_value(name: str, default: str = "") -> str:
    value = st.query_params.get(name, default)
    return str(value) if value is not None else default


def set_query(**values: str | None) -> None:
    next_values = {key: str(value) for key, value in values.items() if value not in (None, "")}
    st.query_params.clear()
    st.query_params.update(next_values)


def clear_data_cache() -> None:
    load_data.clear()


def switch(name: str) -> None:
    """Navigate using stable page paths instead of session-held page objects."""
    pages = {
        "home": "pages/home.py",
        "products": "pages/products.py",
        "compare": "pages/compare.py",
        "research": "pages/research.py",
        "queue": "pages/queue.py",
        "runs": "pages/runs.py",
        "integrations": "pages/integrations.py",
        "help": "pages/help.py",
    }
    st.switch_page(pages[name])


@st.cache_data(ttl=10)
def load_data(root_text: str) -> dict[str, Any]:
    root = Path(root_text)
    output = root / "output"
    coverage_by_key: dict[str, dict[str, str]] = {}
    for row in read_csv(output / "model_coverage.csv"):
        key = row.get("group_key", "").strip()
        if key and key not in coverage_by_key:
            coverage_by_key[key] = row
    benchmark_by_key = {row.get("group_key", ""): row for row in read_csv(output / "model_benchmark.csv") if row.get("group_key", "")}
    contexts: dict[str, dict[str, Any]] = {}
    groups_dir = output / "model_groups"
    if groups_dir.exists():
        for group_path in sorted(groups_dir.glob("*/group.json")):
            group = read_json(group_path, {})
            if not isinstance(group, dict):
                continue
            key = str(group.get("group_key", "")).strip()
            if not key or key in contexts:
                continue
            state_path = group_path.parent / "model_state.json"
            state = read_json(state_path, {}) if state_path.exists() else {}
            contexts[key] = {"group": group, "state": state if isinstance(state, dict) else {}, "benchmark": benchmark_by_key.get(key, {}), "folder": group_path.parent.name, "has_state": state_path.exists()}
    models: list[dict[str, Any]] = []
    for key, context in contexts.items():
        group = context["group"]
        coverage = coverage_by_key.get(key, {})
        sources = group.get("sources", group.get("offers", []))
        sources = sources if isinstance(sources, list) else []
        marketplaces = sorted({str(source.get("marketplace", "")) for source in sources if isinstance(source, dict) and source.get("marketplace")})
        if not sources:
            catalog_status = "no_sources"
        elif context["has_state"] and coverage:
            catalog_status = "ready"
        elif context["has_state"]:
            catalog_status = "analyzed_no_coverage"
        else:
            catalog_status = "waiting_for_analysis"
        models.append({
            **coverage,
            "group_key": key,
            "brand": str(group.get("brand") or coverage.get("brand") or "—"),
            "model": str(group.get("model") or coverage.get("model") or "—"),
            "marketplaces": marketplaces,
            "marketplace": ", ".join(marketplaces) or "—",
            "sources_total": len(sources),
            "catalog_status": catalog_status,
            "coverage_percent": number(coverage.get("coverage_percent")) if coverage else None,
            "fields_confirmed": integer(coverage.get("fields_confirmed")) if coverage else None,
            "fields_open": integer(coverage.get("fields_open")) if coverage else None,
            "fields_x": integer(coverage.get("fields_x")) if coverage else None,
            "targeted_search_recommended": str(coverage.get("additional_research_recommended", "")).lower() == "true",
            "research_priority": coverage.get("research_priority", ""),
            "recommendation_reasons": coverage.get("recommendation_reasons", "[]"),
        })
    runs: list[dict[str, Any]] = []
    for path in (output / "research_runs").glob("*.json") if (output / "research_runs").exists() else []:
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("run_id"):
            payload["_path"] = str(path)
            payload["_time"] = parse_datetime(payload.get("started_at")) or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            runs.append(payload)
    runs.sort(key=lambda item: item["_time"], reverse=True)
    return {"root": root, "models": sorted(models, key=lambda item: model_name(item)), "contexts": contexts, "runs": runs, "queue": read_csv(output / "firecrawl_offer_queue.csv")}


def current_data() -> dict[str, Any]:
    return load_data(str(data_root()))


def model_by_key(data: dict[str, Any], group_key: str) -> dict[str, Any] | None:
    return next((model for model in data["models"] if model["group_key"] == group_key), None)


def source_lookup(context: dict[str, Any]) -> dict[str, dict[str, str]]:
    sources = context.get("group", {}).get("sources", []) if isinstance(context.get("group"), dict) else []
    result: dict[str, dict[str, str]] = {}
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            continue
        offer_id = str(source.get("external_offer_id") or source.get("offer_id") or "")
        item = {"source_id": str(source.get("source_id", "")), "marketplace": str(source.get("marketplace", "")), "external_offer_id": offer_id, "source_url": str(source.get("source_url") or source.get("normalized_url") or "")}
        if item["source_id"]:
            result[item["source_id"]] = item
        if offer_id:
            result.setdefault(f"offer:{offer_id}", item)
    return result


def field_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    fields = context.get("state", {}).get("fields", {}) if isinstance(context.get("state"), dict) else {}
    lookup = source_lookup(context)
    rows: list[dict[str, Any]] = []
    for name in BENCHMARK_FIELDS:
        item = fields.get(name, {}) if isinstance(fields, dict) else {}
        item = item if isinstance(item, dict) else {}
        value = str(item.get("value", "X") or "X")
        evidence: list[dict[str, str]] = []
        for raw in normalize_evidence(item.get("evidence"), value):
            fallback = lookup.get(raw["source_id"]) or lookup.get(f"offer:{raw['external_offer_id']}") or {}
            evidence.append({**fallback, **{key: raw.get(key) or fallback.get(key, "") for key in raw}})
        rows.append({"field": name, "value": value, "status": "X" if value == "X" else str(item.get("status", "open") or "open"), "confidence": str(item.get("confidence", "low") or "low"), "locked": bool(item.get("locked")), "evidence": evidence, "reason": str(item.get("reason", "") or "")})
    return rows


def model_sources(context: dict[str, Any]) -> list[dict[str, str]]:
    unique: dict[str, dict[str, str]] = {}
    for source in source_lookup(context).values():
        identifier = source.get("source_id") or source.get("external_offer_id") or source.get("source_url")
        if identifier:
            unique[identifier] = source
    return list(unique.values())
