"""Selective, idempotent migration of a versioned JSON fixture into repositories."""
from __future__ import annotations
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MigrationReport:
    products: int = 0; sources: int = 0; links: int = 0; evidence: int = 0
    rejected: list[dict[str, str]] = field(default_factory=list)
    lionelo_ids: set[str] = field(default_factory=set)

def _reject(report: MigrationReport, kind: str, identifier: object, reason: str) -> None:
    report.rejected.append({"kind": kind, "id": str(identifier), "reason": reason})

def migrate(payload: dict[str, Any], catalog: Any, sources: Any) -> MigrationReport:
    report, accepted = MigrationReport(), set()
    for product in payload.get("products", []):
        product_id = str(product.get("product_id", ""))
        is_lionelo = bool(product.get("is_lionelo")) or str(product.get("brand", "")).strip().casefold() == "lionelo"
        invalid = not product_id or product.get("placeholder") or product.get("category_classification_status") == "requires_classification" or "accessory" in str(product.get("category", "")).lower()
        if invalid:
            _reject(report, "product", product_id, "ineligible_catalog_record"); continue
        catalog.upsert_brand(str(product.get("brand_slug") or product.get("brand", "")).lower(), str(product.get("brand", "")))
        canonical = {key: product.get(key, "") for key in ("product_id", "brand", "model", "product_slug", "group_key", "category_key", "is_lionelo")}
        canonical["configuration"] = product.get("configuration", product.get("config", ""))
        canonical["benchmark_group_key"] = product.get("benchmark_group_key", product.get("benchmark_group", ""))
        canonical["status"] = {"refresh_recommended": "active", "waiting_for_analysis": "draft"}.get(str(product.get("status", "")), str(product.get("status", "draft") or "draft"))
        canonical["is_lionelo"] = is_lionelo
        catalog.upsert_product(canonical)
        accepted.add(product_id); report.products += 1
        if is_lionelo: report.lionelo_ids.add(product_id)
    source_ids = set()
    for source in payload.get("sources", []):
        source_id = str(source.get("source_id", ""))
        if source_id:
            sources.upsert_source({key: source.get(key) for key in ("source_id", "source_type", "marketplace", "offer_id", "canonical_url", "original_url", "domain", "content_hash") if key in source}); source_ids.add(source_id); report.sources += 1
    link_ids = set()
    for link in payload.get("links", []):
        link_id, product_id, source_id = str(link.get("link_id", "")), str(link.get("product_id", "")), str(link.get("source_id", ""))
        if product_id in accepted and source_id in source_ids and link_id:
            sources.upsert_link({key: link.get(key) for key in ("link_id", "product_id", "source_id", "group_key", "role") if key in link}); link_ids.add(link_id); report.links += 1
        else: _reject(report, "link", link_id, "invalid_product_or_source_reference")
    for evidence in payload.get("evidence", []):
        link = next((item for item in payload.get("links", []) if item.get("link_id") == evidence.get("product_source_link_id")), {})
        evidence_id = str(evidence.get("evidence_id", ""))
        if evidence_id and evidence.get("product_source_link_id") in link_ids and link.get("product_id") == evidence.get("product_id") and link.get("source_id") == evidence.get("source_id"):
            sources.upsert_evidence({key: evidence.get(key) for key in ("evidence_id", "product_id", "source_id", "product_source_link_id", "field_name", "normalized_field_name", "value", "normalized_value", "excerpt", "evidence_status", "validation_status", "confidence") if key in evidence}); report.evidence += 1
        else: _reject(report, "evidence", evidence_id, "invalid_provenance_reference")
    return report

def load_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"));
    if not isinstance(value, dict) or value.get("schema_version") != "1": raise ValueError("Expected versioned migration fixture")
    return value

def run_migration(payload: dict[str, Any], catalog: Any, sources: Any) -> dict[str, Any]:
    from audit_supabase_migration import audit
    report = migrate(payload, catalog, sources)
    return {**audit(report), "products": report.products, "sources": report.sources, "links": report.links, "evidence": report.evidence}

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[1] / "fixtures/unit3/validated_state_v1.json")
    args = parser.parse_args(argv)
    payload = load_fixture(args.input)
    api_root = Path(__file__).resolve().parents[1] / "fieldnote-api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))
    from repositories.catalog_repository import CatalogRepository
    from repositories.source_repository import SourceRepository
    from repositories.supabase_client import SupabaseClient
    client = SupabaseClient.from_env()
    result = run_migration(payload, CatalogRepository(client), SourceRepository(client))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "pass" else 2

if __name__ == "__main__":
    raise SystemExit(main())
