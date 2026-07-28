"""Opt-in executable contracts for the local Supabase stack.

Run only against `supabase start` with
`FIELDNOTE_SUPABASE_INTEGRATION=1`; the normal offline gate must not need
Docker, local Postgres or a Supabase service-role key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_ENABLED = os.environ.get("FIELDNOTE_SUPABASE_INTEGRATION") == "1"


def query(sql: str, *, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["supabase", "db", "query", "--local", sql],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if expect_success and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    if not expect_success and not result.returncode:
        raise AssertionError("SQL unexpectedly succeeded")
    return result


def run_seed(path: Path) -> None:
    sql = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    for statement in sql.split(";"):
        if statement.strip():
            query(statement)


def seed_statements(path: Path) -> str:
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )


def local_supabase_env() -> dict[str, str]:
    result = subprocess.run(
        ["supabase", "status", "-o", "env"], cwd=ROOT, text=True, capture_output=True, check=True
    )
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    return values


def jwt_for(subject: str, secret: str) -> str:
    def encode(value: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=").decode()

    header = encode({"alg": "HS256", "typ": "JWT"})
    payload = encode({"aud": "authenticated", "exp": 1983812996, "iss": "supabase-demo", "role": "authenticated", "sub": subject})
    signature = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def storage_request(method: str, url: str, token: str, api_key: str, body: bytes = b"") -> tuple[int, str]:
    request = Request(
        url,
        data=body or None,
        method=method,
        headers={"Authorization": f"Bearer {token}", "apikey": api_key},
    )
    if body:
        request.add_header("Content-Type", "application/json" if body.startswith(b"{") else "text/plain")
    try:
        with urlopen(request) as response:
            return response.status, ""
    except HTTPError as error:
        try:
            return int(error.code), error.read().decode("utf-8", errors="replace")
        finally:
            error.close()


def rest_request(method: str, url: str, token: str | None, api_key: str, body: dict[str, object] | None = None) -> tuple[int, str]:
    encoded = json.dumps(body).encode() if body is not None else None
    headers = {"apikey": api_key}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if encoded is not None:
        headers.update({"Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=representation"})
    request = Request(url, data=encoded, method=method, headers=headers)
    try:
        with urlopen(request) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        try:
            return int(error.code), error.read().decode("utf-8", errors="replace")
        finally:
            error.close()


def is_storage_denied(result: tuple[int, str]) -> bool:
    return result[0] in {401, 403, 404} or (
        result[0] == 400 and ("row-level security" in result[1] or '"statusCode":"404"' in result[1])
    )


@unittest.skipUnless(INTEGRATION_ENABLED, "requires local Supabase integration stack")
class SupabaseRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        query("delete from public.sources where source_id = 'runtime-analyst-write'")
        for user_id, role in (("101", "viewer"), ("102", "analyst"), ("103", "admin")):
            full_id = f"00000000-0000-0000-0000-000000000{user_id}"
            query(
                "insert into auth.users (id, aud, role, email, raw_app_meta_data, raw_user_meta_data, created_at, updated_at) "
                f"values ('{full_id}', 'authenticated', 'authenticated', '{role}-runtime@fieldnote.test', '{{}}'::jsonb, '{{}}'::jsonb, now(), now()) "
                "on conflict (id) do nothing"
            )
            query(
                "insert into public.profiles (id, role, must_change_password) "
                f"values ('{full_id}', '{role}', false) "
                "on conflict (id) do update set role = excluded.role, must_change_password = false"
            )

    def test_seed_files_are_idempotent(self) -> None:
        development_seed = seed_statements(ROOT / "supabase" / "seed.sql")
        e2e_seed = seed_statements(ROOT / "e2e" / "seeds" / "fieldnote-stroller-mvp-seed.sql")
        query(
            f"""
            do $$
            declare
              development_brand_before uuid;
              development_product_before uuid;
              e2e_brand_before uuid;
              e2e_product_before uuid;
            begin
              {development_seed}
              {e2e_seed}
              select id into development_brand_before from public.brands where brand_key = 'lionelo';
              select id into development_product_before from public.products where product_id = 'product:lionelo:seed-stroller:';
              select id into e2e_brand_before from public.brands where brand_key = 'fixture-brand';
              select id into e2e_product_before from public.products where product_id = 'product:fixture:stroller:';
              {development_seed}
              {e2e_seed}
              if (select count(*) from public.products where product_id = 'product:lionelo:seed-stroller:') <> 1 then
                raise exception 'development seed is not idempotent';
              end if;
              if (select count(*) from public.products where product_id = 'product:fixture:stroller:') <> 1 then
                raise exception 'E2E seed is not idempotent';
              end if;
              if development_brand_before is distinct from (select id from public.brands where brand_key = 'lionelo')
                 or development_product_before is distinct from (select id from public.products where product_id = 'product:lionelo:seed-stroller:')
                 or e2e_brand_before is distinct from (select id from public.brands where brand_key = 'fixture-brand')
                 or e2e_product_before is distinct from (select id from public.products where product_id = 'product:fixture:stroller:') then
                raise exception 'seed rerun changed stable UUIDs';
              end if;
            end $$;
            """
        )

    def test_evidence_link_mismatch_is_rejected(self) -> None:
        query(
            """
            do $$ begin
              insert into public.brands (brand_key, display_name) values ('runtime-evidence', 'Runtime Evidence') on conflict do nothing;
              insert into public.products (product_id, brand_id, brand, model, product_slug, group_key)
                select 'product:runtime:evidence-a', id, 'Runtime Evidence', 'A', 'runtime-evidence-a', 'runtime|evidence-a' from public.brands where brand_key = 'runtime-evidence'
                on conflict (product_id) do nothing;
              insert into public.products (product_id, brand_id, brand, model, product_slug, group_key)
                select 'product:runtime:evidence-b', id, 'Runtime Evidence', 'B', 'runtime-evidence-b', 'runtime|evidence-b' from public.brands where brand_key = 'runtime-evidence'
                on conflict (product_id) do nothing;
              insert into public.sources (source_id) values ('runtime-source-x'), ('runtime-source-y') on conflict do nothing;
              insert into public.product_source_links (link_id, product_id, source_id)
                values ('runtime-link-b-y', 'product:runtime:evidence-b', 'runtime-source-y') on conflict do nothing;
              insert into public.evidence_items (evidence_id, product_id, source_id, product_source_link_id, field_name, normalized_field_name, evidence_status)
                values ('runtime-evidence-valid', 'product:runtime:evidence-b', 'runtime-source-y', 'runtime-link-b-y', 'weight', 'weight', 'valid')
                on conflict (evidence_id) do nothing;
              begin
                insert into public.evidence_items (evidence_id, product_id, source_id, product_source_link_id, field_name, normalized_field_name, evidence_status)
                values ('runtime-evidence-mismatch', 'product:runtime:evidence-a', 'runtime-source-x', 'runtime-link-b-y', 'weight', 'weight', 'valid');
                raise exception 'mismatched evidence link unexpectedly accepted';
              exception when check_violation then null;
              end;
              begin
                update public.product_source_links set product_id = 'product:runtime:evidence-a', source_id = 'runtime-source-x'
                 where link_id = 'runtime-link-b-y';
                raise exception 'evidence-backed link unexpectedly changed provenance';
              exception when check_violation then null;
              end;
            end $$;
            """
        )

    def test_roles_storage_and_audit_actor_are_enforced(self) -> None:
        query(
            """
            do $$ begin
              perform set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000101', true);
              perform set_config('request.jwt.claim.role', 'authenticated', true);
              set local role authenticated;
              if not public.fieldnote_can_read() or public.fieldnote_can_write_data() or public.fieldnote_is_admin() then
                raise exception 'viewer role contract failed';
              end if;
              reset role;
              perform set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000102', true);
              set local role authenticated;
              if not public.fieldnote_can_write_data() or public.fieldnote_is_admin() then
                raise exception 'analyst role contract failed';
              end if;
              begin
                insert into public.audit_events (actor_id, event_type, entity_type, entity_id)
                values ('00000000-0000-0000-0000-000000000103', 'runtime', 'test', 'spoof');
                raise exception 'spoofed audit actor unexpectedly accepted';
              exception when insufficient_privilege then null;
              end;
              reset role;
              perform set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000103', true);
              set local role authenticated;
              if not public.fieldnote_is_admin() then raise exception 'admin role contract failed'; end if;
              reset role;
            end $$;
            """
        )

    def test_storage_api_enforces_viewer_analyst_and_admin_roles(self) -> None:
        environment = local_supabase_env()
        base_url = environment["API_URL"] + "/storage/v1/object/imports"
        viewer = jwt_for("00000000-0000-0000-0000-000000000101", environment["JWT_SECRET"])
        analyst = jwt_for("00000000-0000-0000-0000-000000000102", environment["JWT_SECRET"])
        admin = jwt_for("00000000-0000-0000-0000-000000000103", environment["JWT_SECRET"])
        object_name = "runtime-role-contract.txt"

        api_key = environment["ANON_KEY"]
        storage_request("DELETE", base_url, admin, api_key, json.dumps({"prefixes": [object_name]}).encode())
        viewer_upload = storage_request("POST", f"{base_url}/{object_name}", viewer, api_key, b"viewer")
        self.assertTrue(is_storage_denied(viewer_upload), viewer_upload[1])
        analyst_upload = storage_request("POST", f"{base_url}/{object_name}", analyst, api_key, b"analyst")
        self.assertIn(analyst_upload[0], {200, 201}, analyst_upload[1])
        viewer_read = storage_request("GET", f"{base_url}/{object_name}", viewer, api_key)
        self.assertTrue(is_storage_denied(viewer_read), viewer_read[1])
        admin_delete = storage_request("DELETE", base_url, admin, api_key, json.dumps({"prefixes": [object_name]}).encode())
        self.assertIn(admin_delete[0], {200, 204}, admin_delete[1])

    def test_postgrest_enforces_anon_viewer_analyst_and_admin_boundaries(self) -> None:
        environment = local_supabase_env()
        rest_url = environment["API_URL"] + "/rest/v1"
        api_key = environment["ANON_KEY"]
        viewer = jwt_for("00000000-0000-0000-0000-000000000101", environment["JWT_SECRET"])
        analyst = jwt_for("00000000-0000-0000-0000-000000000102", environment["JWT_SECRET"])
        admin = jwt_for("00000000-0000-0000-0000-000000000103", environment["JWT_SECRET"])

        anon_read = rest_request("GET", f"{rest_url}/products?select=product_id&limit=1", None, api_key)
        self.assertIn(anon_read[0], {401, 403}, anon_read[1])
        viewer_read = rest_request("GET", f"{rest_url}/products?select=product_id&limit=1", viewer, api_key)
        self.assertEqual(viewer_read[0], 200, viewer_read[1])
        viewer_write = rest_request(
            "POST", f"{rest_url}/sources", viewer, api_key, {"source_id": "runtime-viewer-write"}
        )
        self.assertIn(viewer_write[0], {401, 403}, viewer_write[1])
        analyst_write = rest_request(
            "POST", f"{rest_url}/sources", analyst, api_key, {"source_id": "runtime-analyst-write"}
        )
        self.assertIn(analyst_write[0], {200, 201}, analyst_write[1])
        analyst_catalog_write = rest_request(
            "POST", f"{rest_url}/brands?on_conflict=brand_key", analyst, api_key,
            {"brand_key": "runtime-admin-catalog", "display_name": "Runtime Admin Catalog"},
        )
        self.assertIn(analyst_catalog_write[0], {401, 403}, analyst_catalog_write[1])
        admin_catalog_write = rest_request(
            "POST", f"{rest_url}/brands?on_conflict=brand_key", admin, api_key,
            {"brand_key": "runtime-admin-catalog", "display_name": "Runtime Admin Catalog"},
        )
        self.assertIn(admin_catalog_write[0], {200, 201}, admin_catalog_write[1])
        admin_catalog_rerun = rest_request(
            "POST", f"{rest_url}/brands?on_conflict=brand_key", admin, api_key,
            {"brand_key": "runtime-admin-catalog", "display_name": "Runtime Admin Catalog"},
        )
        self.assertIn(admin_catalog_rerun[0], {200, 201}, admin_catalog_rerun[1])
        admin_catalog_read = rest_request(
            "GET", f"{rest_url}/brands?brand_key=eq.runtime-admin-catalog&select=id,brand_key", admin, api_key
        )
        self.assertEqual(admin_catalog_read[0], 200, admin_catalog_read[1])
        self.assertEqual(len(json.loads(admin_catalog_read[1])), 1)
        viewer_profile_manage = rest_request(
            "POST", f"{rest_url}/profiles", viewer, api_key,
            {"id": "00000000-0000-0000-0000-000000000104", "role": "viewer", "must_change_password": True},
        )
        self.assertIn(viewer_profile_manage[0], {401, 403}, viewer_profile_manage[1])
        query(
            "insert into auth.users (id, aud, role, email, raw_app_meta_data, raw_user_meta_data, created_at, updated_at) "
            "values ('00000000-0000-0000-0000-000000000104', 'authenticated', 'authenticated', 'managed-runtime@fieldnote.test', '{}'::jsonb, '{}'::jsonb, now(), now()) "
            "on conflict (id) do nothing"
        )
        admin_profile_manage = rest_request(
            "POST", f"{rest_url}/profiles", admin, api_key,
            {"id": "00000000-0000-0000-0000-000000000104", "role": "viewer", "must_change_password": True},
        )
        self.assertIn(admin_profile_manage[0], {200, 201}, admin_profile_manage[1])

    def test_durable_queue_rpc_concurrency_fencing_and_rls(self) -> None:
        """Exercise the real queue RPCs through the local PostgREST boundary."""
        environment = local_supabase_env()
        rest_url = environment["API_URL"] + "/rest/v1"
        service_key = environment["SERVICE_ROLE_KEY"]
        anon_key = environment["ANON_KEY"]
        analyst = jwt_for("00000000-0000-0000-0000-000000000102", environment["JWT_SECRET"])
        requested_by = "00000000-0000-0000-0000-000000000103"
        suffix = hashlib.sha256(os.urandom(16)).hexdigest()[:12]
        product_ids = [f"product:runtime:queue-{suffix}-{index}" for index in range(4)]
        job_ids = [f"runtime-queue-{suffix}-{index}" for index in range(4)]

        def rpc(name: str, payload: dict[str, object]) -> tuple[int, str]:
            return rest_request("POST", f"{rest_url}/rpc/{name}", service_key, service_key, payload)

        def rows(result: tuple[int, str]) -> list[dict[str, object]]:
            self.assertEqual(result[0], 200, result[1])
            value = json.loads(result[1] or "[]")
            return value if isinstance(value, list) else []

        try:
            query(
                "insert into public.brands (brand_key, display_name) values "
                f"('runtime-queue-{suffix}', 'Runtime Queue {suffix}') on conflict (brand_key) do nothing;"
            )
            for product_id in product_ids:
                query(
                    "insert into public.products (product_id, brand_id, brand, model, product_slug, group_key) "
                    f"select '{product_id}', id, 'Runtime Queue', '{product_id.rsplit('-', 1)[-1]}', "
                    f"'{product_id.replace(':', '-')}', 'runtime|queue-{suffix}-{product_id.rsplit('-', 1)[-1]}' from public.brands where brand_key = 'runtime-queue-{suffix}' "
                    "on conflict (product_id) do nothing;"
                )
            for job_id, product_id in zip(job_ids, product_ids):
                query(
                    "insert into public.research_jobs (job_id, product_id, requested_by, payload) "
                    f"values ('{job_id}', '{product_id}', '{requested_by}', '{{\"limits\":{{\"max_retries\":2}}}}'::jsonb) "
                    "on conflict (job_id) do nothing;"
                )

            # Four independent HTTP requests contend for three queued jobs;
            # the database advisory lock and active-slot count must admit two.
            def claim(worker: str) -> tuple[int, str]:
                return rpc(
                    "fieldnote_claim_research_job",
                    {"p_worker_id": worker, "p_lease_seconds": 10, "p_max_active": 2},
                )

            with ThreadPoolExecutor(max_workers=4) as pool:
                claim_results = list(pool.map(claim, [f"runtime-worker-{index}" for index in range(4)]))
            claimed = [item for result in claim_results for item in rows(result)]
            self.assertEqual(len(claimed), 2)
            self.assertEqual(len({item["job_id"] for item in claimed}), 2)
            self.assertEqual({item["status"] for item in claimed}, {"leased"})

            # Finish the first two claims so a single queued job can be raced.
            for item in claimed:
                rows(rpc("fieldnote_complete_research_job", {
                    "p_job_id": item["job_id"], "p_lease_token": item["lease_token"],
                    "p_status": "succeeded", "p_result": {}, "p_usage": {}, "p_cost_used": 0,
                }))

            # A single queued row has exactly one winner even under contention.
            race_job = job_ids[2]
            with ThreadPoolExecutor(max_workers=3) as pool:
                race_results = list(pool.map(
                    lambda worker: rpc("fieldnote_claim_research_job", {
                        "p_worker_id": worker, "p_lease_seconds": 10, "p_max_active": 1,
                    }), ["race-a", "race-b", "race-c"]
                ))
            race_claims = [item for result in race_results for item in rows(result)]
            self.assertEqual(len(race_claims), 1)
            self.assertEqual(race_claims[0].get("job_id"), race_job)

            # Expiry/reclaim fences the previous token from heartbeat and completion.
            old_token = race_claims[0]["lease_token"]
            query(f"update public.research_jobs set lease_expires_at = now() - interval '1 second' where job_id = '{race_job}'")
            reclaimed = rows(rpc("fieldnote_claim_research_job", {"p_worker_id": "reclaimer", "p_lease_seconds": 10, "p_max_active": 2}))
            reclaimed_row = next(item for item in reclaimed if item.get("job_id") == race_job)
            self.assertNotEqual(old_token, reclaimed_row["lease_token"])
            stale_heartbeat = rpc("fieldnote_heartbeat_research_job", {
                "p_job_id": race_job, "p_lease_token": old_token, "p_lease_seconds": 10,
            })
            self.assertEqual(stale_heartbeat[0], 200)
            self.assertEqual(json.loads(stale_heartbeat[1] or "[]"), [])
            stale_start = rpc("fieldnote_start_research_job", {
                "p_job_id": race_job, "p_lease_token": old_token,
            })
            self.assertEqual(stale_start[0], 200)
            self.assertEqual(json.loads(stale_start[1] or "[]"), [])
            current_start = rows(rpc("fieldnote_start_research_job", {
                "p_job_id": race_job, "p_lease_token": reclaimed_row["lease_token"],
            }))
            self.assertEqual(len(current_start), 1)
            self.assertEqual(current_start[0].get("status"), "running")
            stale_complete = rpc("fieldnote_complete_research_job", {
                "p_job_id": race_job, "p_lease_token": old_token, "p_status": "succeeded",
                "p_result": {}, "p_usage": {}, "p_cost_used": 0,
            })
            self.assertEqual(stale_complete[0], 200)
            self.assertEqual(json.loads(stale_complete[1] or "[]"), [])
            rows(rpc("fieldnote_complete_research_job", {
                "p_job_id": race_job, "p_lease_token": reclaimed_row["lease_token"],
                "p_status": "succeeded", "p_result": {}, "p_usage": {}, "p_cost_used": 0,
            }))

            # A cancelled lease that expires must become terminal, not an
            # unreachable queued row that keeps the product unique index busy.
            cancelled_job = job_ids[3]
            cancelled_claim = rows(rpc("fieldnote_claim_research_job", {
                "p_worker_id": "cancel-worker", "p_lease_seconds": 10, "p_max_active": 2,
            }))
            cancelled_row = next(item for item in cancelled_claim if item.get("job_id") == cancelled_job)
            self.assertEqual(cancelled_row.get("status"), "leased")
            duplicate_job = f"runtime-duplicate-{suffix}"
            duplicate_attempt = query(
                "insert into public.research_jobs (job_id, product_id, requested_by, payload) "
                f"values ('{duplicate_job}', '{product_ids[3]}', '{requested_by}', '{{\"limits\":{{\"max_retries\":2}}}}'::jsonb)",
                expect_success=False,
            )
            self.assertIn(
                "research_jobs_one_active_per_product",
                f"{duplicate_attempt.stderr}\n{duplicate_attempt.stdout}",
            )
            rows(rpc("fieldnote_request_research_job_cancel", {"p_job_id": cancelled_job}))
            query(f"update public.research_jobs set lease_expires_at = now() - interval '1 second' where job_id = '{cancelled_job}'")
            rows(rpc("fieldnote_claim_research_job", {"p_worker_id": "cancel-recovery", "p_lease_seconds": 10, "p_max_active": 2}))
            query(
                "do $$ begin "
                f"if not exists (select 1 from public.research_jobs where job_id = '{cancelled_job}' and status = 'cancelled' and completed_at is not null) "
                "then raise exception 'expired cancelled job was not terminalized'; end if; end $$;"
            )
            replacement_job = f"runtime-replacement-{suffix}"
            query(
                "insert into public.research_jobs (job_id, product_id, requested_by, payload) "
                f"values ('{replacement_job}', '{product_ids[3]}', '{requested_by}', '{{\"limits\":{{\"max_retries\":2}}}}'::jsonb)"
            )

            # Queue tables are server-owned: browser roles cannot mutate either table.
            for token in (None, analyst):
                for method, query_suffix, body in (
                    ("POST", "", {"job_id": f"runtime-denied-{suffix}", "product_id": product_ids[3], "requested_by": requested_by}),
                    ("PATCH", f"?job_id=eq.{job_ids[0]}", {"result": {"spoof": True}}),
                    ("DELETE", f"?job_id=eq.{job_ids[0]}", None),
                ):
                    denied_job = rest_request(method, f"{rest_url}/research_jobs{query_suffix}", token, anon_key, body)
                    self.assertIn(denied_job[0], {401, 403}, denied_job[1])
                for method, query_suffix, body in (
                    ("POST", "", {"job_id": claimed[0]["id"], "event_type": "spoof"}),
                    ("PATCH", f"?id=eq.0", {"event_type": "spoof"}),
                    ("DELETE", f"?id=eq.0", None),
                ):
                    denied_event = rest_request(method, f"{rest_url}/research_job_events{query_suffix}", token, anon_key, body)
                    self.assertIn(denied_event[0], {401, 403}, denied_event[1])
        finally:
            query(f"delete from public.research_jobs where job_id like 'runtime-%-{suffix}%'")
            query(f"delete from public.products where product_id like 'product:runtime:queue-{suffix}-%'")
            query(f"delete from public.brands where brand_key = 'runtime-queue-{suffix}'")
