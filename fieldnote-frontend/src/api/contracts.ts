export type EvidenceStatusV1 = "valid" | "weak" | "conflicting" | "rejected" | "unattributed_legacy" | "invalid_reference";

export interface EvidenceItemV1 {
  schema_version: "1";
  evidence_id: string;
  product_slug: string;
  field_name: string;
  normalized_field_name: string;
  value: string | null;
  normalized_value: string | null;
  source_id: string | null;
  product_source_link_id: string | null;
  excerpt: string;
  evidence_status: EvidenceStatusV1;
  validation_status: string;
  confidence: "high" | "medium" | "low" | "unknown";
  source_authority: "manufacturer" | "marketplace" | "other" | "unknown";
  content_family_id: string | null;
  confirmation_weight: number;
  is_independent_confirmation: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductMetricsV1 {
  schema_version: "1";
  coverage_percent: number | null;
  evidence_quality_percent: number | null;
  source_confidence_percent: number | null;
  fields_total: number | null;
  fields_present: number | null;
  fields_missing: number | null;
  fields_valid: number;
  fields_weak: number;
  fields_conflicting: number;
  fields_rejected: number;
  fields_unattributed: number;
  high_confidence_fields: number;
  analysis_complete: boolean;
  weak_fields?: number;
  conflicting_fields?: number;
  unattributed_legacy_fields?: number;
  missing_fields?: number | null;
}

export interface SourceContributionV1 {
  schema_version: "1";
  source_id: string;
  product_slug: string;
  new_fields: Array<{ field_name: string; value: string; excerpt: string }>;
  /** Legacy API alias, retained while older local snapshots are read. */
  unique_fields_contributed?: Array<{ field_name: string; value: string; excerpt: string }>;
  confirmed_fields: Array<{ field_name: string; value: string; excerpt: string }>;
  conflicting_fields: Array<{ field_name: string; value: string; excerpt: string }>;
  rejected_evidence: Array<{ field_name: string; value: string; excerpt: string }>;
  final_fields_used: Array<{ field_name: string; value: string; excerpt: string }>;
  used_fields_count: number;
  independent_confirmations_count: number;
  content_families_count: number;
  has_contribution: boolean;
}

export interface ProductV1 {
  schema_version: "1";
  product_slug: string;
  group_key: string;
  brand: string;
  model: string;
  status: string;
  metrics: ProductMetricsV1 | null;
}

export interface SourceRecordV2 {
  schema_version: "2";
  source_id: string;
  source_type: string;
  marketplace: string | null;
  offer_id: string | null;
  canonical_url: string | null;
  original_url: string | null;
  domain: string | null;
}

export interface ProductSourceLinkV1 {
  schema_version: "1";
  link_id: string;
  product_slug: string;
  source_id: string;
  group_key: string;
}

export interface RunManifestV1 {
  schema_version: "1";
  run_id: string;
  status: string;
  product_slug: string;
  group_key: string;
  current_step: string;
  progress: number;
}

export interface BenchmarkV1 {
  schema_version: "1";
  product_slug: string;
  benchmark_category: string;
  fields: string[];
  models: Array<Record<string, unknown>>;
}

export interface PageV1<T> {
  schema_version: "1";
  total: number;
  limit: number;
  offset: number;
  items: T[];
}
