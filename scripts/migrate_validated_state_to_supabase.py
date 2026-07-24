"""Selective, idempotent migration of a versioned JSON fixture into repositories."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MigrationReport:
    products: int = 0; sources: int = 0; links: int = 0; evidence: int = 0
    rejected: list[dict[str, str]] = field(default_factory=list)

def _reject(report: MigrationReport, kind: str, identifier: object, reason: str) -> None:
    report.rejected.append({"kind": kind, "id": str(identifier), "reason": reason})

def migrate(payload: dict[str, Any], catalog: Any, sources: Any) -> MigrationReport:
    report, accepted = MigrationReport(), set()
    for product in payload.get("products", []):
        product_id = str(product.get("product_id", "")); scope = str(product.get("scope", ""))
        is_lionelo = bool(product.get("is_lionelo")) or scope == "lionelo"
        invalid = not product_id or product.get("placeholder") or product.get("category_classification_status") == "requires_classification" or "accessory" in str(product.get("category", "")).lower()
        if invalid or (not is_lionelo and scope != "competitor"):
            _reject(report, "product", product_id, "ineligible_catalog_record"); continue
        catalog.upsert_brand(str(product.get("brand_slug") or product.get("brand", "")).lower(), str(product.get("brand", "")))
        catalog.upsert_product({key: product.get(key, "") for key in ("product_id", "brand", "model", "configuration", "product_slug", "group_key", "category_key", "benchmark_group_key", "status", "is_lionelo")})
        accepted.add(product_id); report.products += 1
    source_ids = set()
    for source in payload.get("sources", []):
        source_id = str(source.get("source_id", ""))
        if source_id:
            sources.upsert_source(source); source_ids.add(source_id); report.sources += 1
    link_ids = set()
    for link in payload.get("links", []):
        link_id, product_id, source_id = str(link.get("link_id", "")), str(link.get("product_id", "")), str(link.get("source_id", ""))
        if product_id in accepted and source_id in source_ids and link_id:
            sources.upsert_link(link); link_ids.add(link_id); report.links += 1
        else: _reject(report, "link", link_id, "invalid_product_or_source_reference")
    for evidence in payload.get("evidence", []):
        link = next((item for item in payload.get("links", []) if item.get("link_id") == evidence.get("product_source_link_id")), {})
        evidence_id = str(evidence.get("evidence_id", ""))
        if evidence_id and evidence.get("product_source_link_id") in link_ids and link.get("product_id") == evidence.get("product_id") and link.get("source_id") == evidence.get("source_id"):
            sources.upsert_evidence(evidence); report.evidence += 1
        else: _reject(report, "evidence", evidence_id, "invalid_provenance_reference")
    return report

def load_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"));
    if not isinstance(value, dict) or value.get("schema_version") != "1": raise ValueError("Expected versioned migration fixture")
    return value
