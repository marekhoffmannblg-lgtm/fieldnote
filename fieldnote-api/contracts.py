"""Versioned public contracts for the local FIELDNOTE API.

The models are intentionally permissive around historical pipeline payloads:
they standardise the public envelope without rewriting legacy local data.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class V1Model(BaseModel):
    """All public models expose an explicit immutable schema version."""

    model_config = ConfigDict(extra="allow")
    schema_version: Literal["1"] = "1"


class EvidenceItemV1(V1Model):
    evidence_id: str
    product_slug: str
    field_name: str
    normalized_field_name: str
    value: str | None = None
    normalized_value: str | None = None
    source_id: str | None = None
    product_source_link_id: str | None = None
    excerpt: str = ""
    evidence_status: Literal[
        "valid", "weak", "conflicting", "rejected", "unattributed_legacy", "invalid_reference"
    ]
    validation_status: str = ""
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    source_authority: Literal["manufacturer", "marketplace", "other", "unknown"] = "unknown"
    content_family_id: str | None = None
    confirmation_weight: float = 0.0
    is_independent_confirmation: bool = False
    created_at: str = ""
    updated_at: str = ""


class ProductMetricsV1(V1Model):
    coverage_percent: float | None = None
    evidence_quality_percent: float | None = None
    source_confidence_percent: float | None = None
    fields_total: int | None = None
    fields_present: int | None = None
    fields_missing: int | None = None
    fields_valid: int = 0
    fields_weak: int = 0
    fields_conflicting: int = 0
    fields_rejected: int = 0
    fields_unattributed: int = 0
    high_confidence_fields: int = 0
    analysis_complete: bool = False
    # Legacy aliases kept only so existing snapshot payloads remain readable.
    weak_fields: int = 0
    conflicting_fields: int = 0
    unattributed_legacy_fields: int = 0
    missing_fields: int | None = None


class SourceContributionV1(V1Model):
    source_id: str = ""
    product_slug: str = ""
    new_fields: list[dict[str, Any]] = Field(default_factory=list)
    unique_fields_contributed: list[dict[str, Any]] = Field(default_factory=list)
    confirmed_fields: list[dict[str, Any]] = Field(default_factory=list)
    conflicting_fields: list[dict[str, Any]] = Field(default_factory=list)
    rejected_evidence: list[dict[str, Any]] = Field(default_factory=list)
    final_fields_used: list[dict[str, Any]] = Field(default_factory=list)
    used_fields_count: int = 0
    independent_confirmations_count: int = 0
    content_families_count: int = 0
    has_contribution: bool = False


class ProductV1(V1Model):
    product_slug: str
    group_key: str = ""
    brand: str = ""
    model: str = ""
    status: str = ""
    metrics: ProductMetricsV1 | None = None


class SourceRecordV2(V1Model):
    schema_version: Literal["2"] = "2"
    source_id: str
    source_type: str = "other"
    marketplace: str | None = None
    offer_id: str | None = None
    canonical_url: str | None = None
    original_url: str | None = None
    domain: str | None = None


class ProductSourceLinkV1(V1Model):
    link_id: str
    product_slug: str
    source_id: str
    group_key: str = ""


class RunManifestV1(V1Model):
    run_id: str
    status: str
    product_slug: str = ""
    group_key: str = ""
    current_step: str = ""
    progress: int = 0


class BenchmarkV1(V1Model):
    product_slug: str
    benchmark_category: str = ""
    fields: list[str] = Field(default_factory=list)
    models: list[dict[str, Any]] = Field(default_factory=list)


T = TypeVar("T")


class PageV1(V1Model, Generic[T]):
    total: int
    limit: int
    offset: int
    items: list[T] = Field(default_factory=list)
