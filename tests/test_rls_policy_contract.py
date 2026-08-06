"""Offline security contracts for Supabase roles, RLS and private storage."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RLS = (ROOT / "supabase" / "migrations" / "202607230005_auth_roles_rls_storage.sql").read_text(encoding="utf-8")


class RlsPolicyContractTests(unittest.TestCase):
    def test_auth_disables_self_signup_and_declares_only_expected_roles(self) -> None:
        config = (ROOT / "supabase" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("enable_signup = false", config)
        self.assertIn("create type public.fieldnote_role as enum ('viewer', 'analyst', 'admin')", (ROOT / "supabase" / "migrations" / "202607230001_core_catalog.sql").read_text(encoding="utf-8"))
        self.assertIn("references auth.users(id) on delete cascade", RLS)
        self.assertIn("must_change_password boolean not null default true", RLS)

    def test_every_business_table_has_rls_and_anon_receives_no_policy(self) -> None:
        tables = (
            "brands", "products", "product_aliases", "product_skus", "attribute_schema_versions",
            "product_profile_overrides", "sources", "product_source_links", "content_families",
            "source_snapshots", "evidence_items", "attribute_values", "attribute_value_candidates",
            "sellers", "offers", "price_observations", "availability_observations",
            "competitive_benchmarks", "competitive_benchmark_participants", "benchmark_results",
            "benchmark_snapshots", "research_jobs", "research_job_events", "import_runs", "audit_events", "profiles",
        )
        for table in tables:
            self.assertIn(f"alter table public.{table} enable row level security;", RLS)
        self.assertNotRegex(RLS.lower(), re.compile(r"create policy\s+\S+.*\bto anon\b"))

    def test_viewer_is_read_only_analyst_writes_data_and_only_admin_manages_profiles(self) -> None:
        self.assertIn("create policy authenticated_read on public.products for select to authenticated", RLS)
        self.assertIn("public.fieldnote_can_read()", RLS)
        self.assertIn("public.fieldnote_can_write_data()", RLS)
        self.assertIn("public.fieldnote_current_role() in ('analyst', 'admin')", RLS)
        self.assertIn("create policy admin_profile_manage on public.profiles for all", RLS)
        self.assertIn("create policy admin_write on public.products for all", RLS)

    def test_private_storage_accepts_only_authorized_roles(self) -> None:
        for bucket in ("source-raw", "source-clean", "imports"):
            self.assertIn(f"('{bucket}', '{bucket}', false, 26214400)", RLS)
        self.assertIn("authenticated_storage_read on storage.objects", RLS)
        self.assertIn(
            "bucket_id in ('source-raw', 'source-clean', 'imports') and public.fieldnote_can_write_data()",
            RLS,
        )
        self.assertIn("analyst_storage_write on storage.objects", RLS)
        self.assertIn("admin_storage_delete on storage.objects", RLS)

    def test_audit_events_bind_the_actor_to_the_authenticated_subject(self) -> None:
        self.assertIn("fieldnote_set_audit_actor", RLS)
        self.assertIn("new.actor_id is distinct from auth.uid()", RLS)
        self.assertIn("new.actor_id := auth.uid()", RLS)

    def test_incremental_snapshot_table_is_rls_protected(self) -> None:
        incremental = (ROOT / "supabase" / "migrations" / "202607290001_incremental_benchmark_commit.sql").read_text(encoding="utf-8")
        self.assertIn("alter table public.research_scope_snapshots enable row level security;", incremental)
        self.assertIn("public.fieldnote_can_read()", incremental)
        self.assertNotRegex(incremental.lower(), re.compile(r"grant\s+(insert|update|delete|all).*research_scope_snapshots.*authenticated"))

    def test_product_refresh_history_tables_are_rls_protected(self) -> None:
        refresh = (ROOT / "supabase" / "migrations" / "202608060001_product_refresh_history.sql").read_text(encoding="utf-8")
        for table in ("product_refresh_runs", "product_refresh_snapshots", "product_refresh_run_sources"):
            self.assertIn(f"alter table public.{table} enable row level security;", refresh)
            self.assertIn(f"public.{table}", refresh)
        self.assertNotRegex(refresh.lower(), re.compile(r"create policy\s+\S+.*\bto anon\b"))


if __name__ == "__main__":
    unittest.main()
