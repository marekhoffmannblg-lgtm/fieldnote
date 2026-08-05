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
    # Visual references are optional contextual pointers. They never turn media
    # into an automatically accepted product fact.
    visual_snapshot_id: str | None = None
    visual_block_id: str | None = None
    media_ids: list[str] = Field(default_factory=list)
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


class CompetitiveBenchmarkCreateRequest(BaseModel):
    benchmark_group_key: str
    anchor_product_id: str
    participant_product_ids: list[str]
    title: str = Field(min_length=1, max_length=160)
    status: Literal["draft", "active", "archived"] = "draft"


class CompetitiveBenchmarkSummary(BaseModel):
    benchmark_id: str
    title: str
    status: Literal["draft", "active", "archived"]
    benchmark_group_key: str
    anchor_product_id: str
    participant_count: int
    created_at: str
    updated_at: str


class BenchmarkProductRef(BaseModel):
    product_id: str
    brand: str
    model: str
    configuration: str = ""
    benchmark_group: str
    product_slug: str
    status: str
    coverage: float | None = None
    source_count: int = 0


class CompetitiveBenchmarkDetail(BaseModel):
    benchmark_id: str
    benchmark_type: Literal["competitive"]
    benchmark_group_key: str
    title: str
    status: Literal["draft", "active", "archived"]
    created_at: str
    updated_at: str
    anchor: BenchmarkProductRef
    participants: list[BenchmarkProductRef] = Field(default_factory=list)
    participant_count: int


class InternalBenchmarkSummary(BaseModel):
    benchmark_id: None = None
    benchmark_type: Literal["internal"] = "internal"
    benchmark_group_key: str
    benchmark_group_label: str
    title: str
    status: Literal["dynamic"] = "dynamic"
    participant_count: int
    has_comparison: bool


class InternalBenchmarkDetail(BaseModel):
    benchmark_id: None = None
    benchmark_type: Literal["internal"] = "internal"
    benchmark_group_key: str
    title: str
    status: Literal["dynamic"] = "dynamic"
    anchor: None = None
    participants: list[BenchmarkProductRef] = Field(default_factory=list)
    participant_count: int
    created_at: None = None
    updated_at: str | None = None


class BenchmarkScoreV1(V1Model):
    product_id: str
    score: float
    completeness: float
    position: int | None = None
    field_contributions: dict[str, float] = Field(default_factory=dict)


class PriceSummaryV1(V1Model):
    status: Literal["ok", "no_data"] = "no_data"
    median: float | None = None
    min: float | None = None
    max: float | None = None
    seller_count: int = 0


# Backward-compatible import name for callers that used the previous detail DTO.
CompetitiveBenchmarkResponse = CompetitiveBenchmarkDetail


class ProductProfileV1(V1Model):
    """Source-backed profile layer, independent from the benchmark state."""
    product_slug: str
    profile_status: Literal["not_generated", "generating", "generated", "partial", "failed", "stale"] = "not_generated"
    profile_version: str = "v1"
    one_sentence_summary: str = ""
    narrative_summary: str = ""
    discovered_themes: list["ProductProfileThemeV1"] = Field(default_factory=list)
    factual_highlights: list["ProductProfileFactV1"] = Field(default_factory=list)
    marketplace_narrative: list["MarketplaceNarrativeV1"] = Field(default_factory=list)
    visual_positioning: list["VisualPositioningV1"] = Field(default_factory=list)
    important_conflicts: list["ProductProfileConflictV1"] = Field(default_factory=list)
    important_unknowns: list["ProductProfileUnknownV1"] = Field(default_factory=list)
    input_summary: "ProductProfileInputSummaryV1" = Field(default_factory=lambda: ProductProfileInputSummaryV1())
    generation: "ProductProfileGenerationV1" = Field(default_factory=lambda: ProductProfileGenerationV1())


class ProductProfileNestedV1(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductProfileThemeV1(ProductProfileNestedV1):
    theme_id: str
    title: str
    summary: str
    basis_types: list[str] = Field(default_factory=list)
    supporting_source_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_visual_block_ids: list[str] = Field(default_factory=list)
    supporting_media_ids: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]


class ProductProfileFactV1(ProductProfileNestedV1):
    statement: str
    field_names: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)


class MarketplaceNarrativeV1(ProductProfileNestedV1):
    observation: str
    supporting_source_ids: list[str] = Field(default_factory=list)
    content_family_ids: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]


class VisualPositioningV1(ProductProfileNestedV1):
    observation: str
    basis: Literal["explicit_image_text", "caption", "visual_scene", "repetition", "mixed", "text_context_only"]
    visual_access: Literal["image_seen", "text_context_only"]
    supporting_visual_block_ids: list[str] = Field(default_factory=list)
    supporting_media_ids: list[str] = Field(default_factory=list)
    supporting_source_ids: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    is_factual_product_claim: Literal[False] = False


class ProductProfileConflictV1(ProductProfileNestedV1):
    summary: str
    field_names: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_source_ids: list[str] = Field(default_factory=list)


class ProductProfileUnknownV1(ProductProfileNestedV1):
    summary: str
    reason: str
    related_source_ids: list[str] = Field(default_factory=list)


class ProductProfileInputSummaryV1(ProductProfileNestedV1):
    sources_used: int = 0
    manufacturer_sources: int = 0
    marketplace_sources: int = 0
    independent_content_families: int = 0
    evidence_items_used: int = 0
    visual_blocks_used: int = 0
    media_items_used: int = 0
    textual_coverage: str = "none"
    visual_coverage: str = "none"


class ProductProfileGenerationV1(ProductProfileNestedV1):
    canonical_input_hash: str = ""
    transmission_payload_hash: str = ""
    cache_key: str = ""
    model_name: str = ""
    prompt_version: str = ""
    schema_version: str = ""
    openai_requests_attempted_this_run: int = 0
    openai_requests_succeeded_this_run: int = 0
    profile_request_count_total: int = 0
    cached: bool = False
    generated_at: str = ""
    failure_code: str = ""
    failure_reason: str = ""
    semantic_profile_nonempty: bool = False
    profile_quality_valid: bool = False
    latest_generation_attempt_status: str = ""
    latest_failure_code: str = ""
    latest_failure_reason: str = ""
    latest_attempt_at: str = ""


ProductProfileV1.model_rebuild()


T = TypeVar("T")


class PageV1(V1Model, Generic[T]):
    total: int
    limit: int
    offset: int
    items: list[T] = Field(default_factory=list)
