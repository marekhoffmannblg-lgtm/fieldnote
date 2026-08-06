"""Offline contracts for the versioned Supabase schema.

These tests intentionally inspect migrations; provisioning Supabase is an
operator concern and must not be required by CI or local offline checks.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"


def migration(name: str) -> str:
    return (MIGRATIONS / name).read_text(encoding="utf-8")


class SupabaseSchemaContractTests(unittest.TestCase):
    def test_migrations_are_ordered_and_cover_the_declared_platform(self) -> None:
        self.assertEqual(
            [path.name for path in sorted(MIGRATIONS.glob("*.sql"))],
            [
                "202607230001_core_catalog.sql",
                "202607230002_sources_provenance.sql",
                "202607230003_market_benchmarks.sql",
                "202607230004_jobs_audit.sql",
                "202607230005_auth_roles_rls_storage.sql",
                "202607280001_durable_research_queue.sql",
                "202607290001_incremental_benchmark_commit.sql",
                "202607300001_incremental_commit_partial_fixes.sql",
                "202608060001_product_refresh_history.sql",
            ],
        )
        schema = "\n".join(migration(path.name) for path in sorted(MIGRATIONS.glob("*.sql")))
        for table in (
            "brands", "products", "product_aliases", "sources", "product_source_links",
            "source_snapshots", "evidence_items", "attribute_values", "offers",
            "price_observations", "competitive_benchmarks", "research_jobs", "profiles",
        ):
            self.assertRegex(schema, rf"create table public\.{table} \(")

    def test_stable_ids_and_shared_source_relationships_are_constrained(self) -> None:
        catalog = migration("202607230001_core_catalog.sql")
        provenance = migration("202607230002_sources_provenance.sql")
        jobs = migration("202607230004_jobs_audit.sql")
        self.assertIn("product_id text not null unique", catalog)
        self.assertIn("group_key text not null unique", catalog)
        self.assertIn("source_id text not null unique", provenance)
        self.assertIn("unique (product_id, source_id)", provenance)
        self.assertIn("fieldnote_validate_evidence_link", provenance)
        self.assertIn("fieldnote_prevent_link_provenance_rewrite", provenance)
        self.assertIn("unique index research_jobs_one_active_per_product", jobs)
        self.assertIn("where status in ('queued', 'leased', 'running')", jobs)

    def test_seed_is_idempotent_and_does_not_create_credentials(self) -> None:
        for path in (ROOT / "supabase" / "seed.sql", ROOT / "e2e" / "seeds" / "fieldnote-stroller-mvp-seed.sql"):
            seed = path.read_text(encoding="utf-8")
            self.assertIn("on conflict", seed.lower())
            self.assertNotRegex(seed, re.compile(r"auth\.users|password|service_role", re.IGNORECASE))

    def test_evidence_link_trigger_requires_one_consistent_provenance_path(self) -> None:
        provenance = migration("202607230002_sources_provenance.sql")
        self.assertIn("fieldnote_validate_evidence_link", provenance)
        self.assertIn("new.product_id is distinct from linked_product_id", provenance)
        self.assertIn("new.source_id is distinct from linked_source_id", provenance)

    def test_incremental_commit_is_fenced_and_serializes_durable_snapshots(self) -> None:
        incremental = migration("202607290001_incremental_benchmark_commit.sql")
        self.assertIn("create table public.research_scope_snapshots", incremental)
        self.assertIn("pg_advisory_xact_lock(hashtext('fieldnote_benchmark_incremental_commit'))", incremental)
        self.assertIn("lease_token = p_lease_token", incremental)
        self.assertIn("scope product does not match fenced job", incremental)
        self.assertIn("abs(candidate_price - previous.price_median) / abs(previous.price_median) >= 0.05", incremental)
        self.assertIn("grant execute on function public.fieldnote_commit_incremental_research_job", incremental)

    def test_incremental_partial_fix_is_a_monotonic_upgrade(self) -> None:
        historical = migration("202607290001_incremental_benchmark_commit.sql")
        upgrade = migration("202607300001_incremental_commit_partial_fixes.sql")
        self.assertIn("if coalesce(p_scope->>'product_id', '') <> value.product_id then", historical)
        self.assertNotIn("no_mutation", historical)
        self.assertIn("create or replace function public.fieldnote_commit_incremental_research_job", upgrade)
        self.assertIn("no_mutation", upgrade)
        self.assertIn("for candidate in select element from jsonb_array_elements(p_snapshots) as elements(element)", upgrade)
        self.assertNotIn("create table public.research_scope_snapshots", upgrade)

    def test_product_refresh_history_has_snapshot_and_per_run_link(self) -> None:
        refresh = migration("202608060001_product_refresh_history.sql")
        self.assertIn("create table public.product_refresh_runs", refresh)
        self.assertIn("create table public.product_refresh_snapshots", refresh)
        self.assertIn("unique (source_id, content_hash)", refresh)
        self.assertIn("create table public.product_refresh_run_sources", refresh)
        self.assertIn("snapshot_id uuid not null", refresh)


if __name__ == "__main__":
    unittest.main()
