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


def is_storage_denied(result: tuple[int, str]) -> bool:
    return result[0] in {401, 403, 404} or (
        result[0] == 400 and ("row-level security" in result[1] or '"statusCode":"404"' in result[1])
    )


@unittest.skipUnless(INTEGRATION_ENABLED, "requires local Supabase integration stack")
class SupabaseRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
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
        for path in (ROOT / "supabase" / "seed.sql", ROOT / "e2e" / "seeds" / "fieldnote-stroller-mvp-seed.sql"):
            for _ in range(2):
                run_seed(path)
        query(
            """
            do $$ begin
              if (select count(*) from public.products where product_id = 'product:lionelo:seed-stroller:') <> 1 then
                raise exception 'development seed is not idempotent';
              end if;
              if (select count(*) from public.products where product_id = 'product:fixture:stroller:') <> 1 then
                raise exception 'E2E seed is not idempotent';
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
              begin
                insert into public.evidence_items (evidence_id, product_id, source_id, product_source_link_id, field_name, normalized_field_name, evidence_status)
                values ('runtime-evidence-mismatch', 'product:runtime:evidence-a', 'runtime-source-x', 'runtime-link-b-y', 'weight', 'weight', 'valid');
                raise exception 'mismatched evidence link unexpectedly accepted';
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
