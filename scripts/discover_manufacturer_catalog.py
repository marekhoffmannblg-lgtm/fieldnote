"""Discover and classify the current manufacturer catalog without hidden records."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from firecrawl_client import FirecrawlClient, FirecrawlError
from normalize_product_aliases import alias_record, normalize_records


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources" / "strollers.yaml"


def load_source_config(path: Path = CONFIG) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return _minimal_yaml(text)


def _minimal_yaml(text: str) -> dict[str, Any]:
    """Parse the intentionally small, dependency-free source config format."""
    result: dict[str, Any] = {"sources": []}
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        indent = len(line) - len(line.lstrip())
        key, value = [part.strip() for part in line.strip().split(":", 1)]
        if key == "- brand":
            current = {"brand": value.strip("'\"")}
            result["sources"].append(current)
            continue
        if indent <= 2:
            if value:
                result[key] = _yaml_value(value)
            continue
        if current is not None:
            current[key] = _yaml_value(value)
    return result


def _yaml_value(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
    return value.strip("'\"")


def classify_catalog_record(record: dict[str, Any]) -> dict[str, Any]:
    item = dict(record)
    title = str(item.get("title") or item.get("name") or item.get("model") or "").strip()
    model = str(item.get("model") or item.get("name") or title).strip()
    brand = str(item.get("brand") or "").strip()
    lowered = f"{title} {model}".casefold()
    accessory = bool(re.search(r"\b(accessory|part|adapter|spare|akcesori|częś|czesc|torba|folia)\b", lowered)) and not bool(re.search(r"\b(stroller|wozek|wózek|spacerow|buggy)\b", lowered))
    if accessory or model.casefold() in {"accessory / part", "accessory", "part"}:
        item.update({"model": model, "catalog_status": "excluded", "exclusion_reason": "accessory_or_part", "product_type": "accessory"})
        return item
    if not brand or not model:
        item.update({"catalog_status": "excluded", "exclusion_reason": "missing_identity", "product_type": "unknown"})
        return item
    group = str(item.get("benchmark_group") or item.get("benchmark_group_key") or "").strip()
    item.update({"brand": brand, "model": model, "catalog_status": "classified" if group else "review_required", "classification_reason": "official_catalog_without_group" if not group else "official_catalog", "product_type": "stroller" if re.search(r"\b(stroller|wozek|wózek|spacerow|buggy)\b", lowered) else "unknown"})
    return alias_record(item)


def records_from_firecrawl_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    values = data.get("products") or data.get("items") or data.get("pages") or data.get("data") or []
    if isinstance(values, dict):
        values = [values]
    return [dict(item) for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def load_fixture_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            records.extend(records_from_firecrawl_response(value))
    return records


def discover_catalog(*, brand: str, fixture_root: Path | None = None, client: FirecrawlClient | None = None, category_url: str | None = None, cache: dict[str, Any] | None = None) -> dict[str, Any]:
    if fixture_root is not None:
        raw = load_fixture_records(fixture_root)
    else:
        if client is None or not category_url:
            raise ValueError("fixture_root albo client + category_url jest wymagany")
        try:
            raw = records_from_firecrawl_response(client.crawl(category_url, cache=cache).data)
        except FirecrawlError as exc:
            return {"schema_version": "1", "brand": brand, "status": "partial", "error": str(exc), "items": [], "counts": {}}
    items = [classify_catalog_record({"brand": brand, **item} if not item.get("brand") else item) for item in raw]
    # De-duplicate only after canonical identity is known; 2w1 and 3w1 remain separate.
    active = normalize_records(item for item in items if item.get("catalog_status") != "excluded")
    excluded = [item for item in items if item.get("catalog_status") == "excluded"]
    report_items = active + excluded
    counts = {"total": len(report_items), "classified": sum(item.get("catalog_status") == "classified" for item in report_items), "review_required": sum(item.get("catalog_status") == "review_required" for item in report_items), "excluded": len(excluded), "unclassified_real_products": 0}
    return {"schema_version": "1", "brand": brand, "status": "success", "items": sorted(report_items, key=lambda item: str(item.get("canonical_key") or item.get("model") or "")), "counts": counts, "quality_gate": "pass" if counts["unclassified_real_products"] == 0 else "review"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline-first manufacturer catalog discovery")
    parser.add_argument("--brand", required=True)
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--category-url")
    args = parser.parse_args()
    report = discover_catalog(brand=args.brand, fixture_root=args.fixture_root, category_url=args.category_url, client=FirecrawlClient() if args.category_url else None)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if report.get("quality_gate") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
