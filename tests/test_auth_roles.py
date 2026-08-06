from __future__ import annotations
import sys
import unittest
from pathlib import Path
from fastapi import HTTPException
from fastapi.testclient import TestClient
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))
from auth.dependencies import SupabaseAuthGateway, require_roles
from auth.roles import Principal
from services.user_service import UserService
import app as api
from unittest.mock import patch

class FakeClient:
    def __init__(self): self.created = None; self.profile = None
    def auth_admin(self, method, path, payload): self.created = (method, path, payload); return {"id": "user-1"}
    def upsert(self, table, payload, conflict): self.profile = (table, payload, conflict); return []
    def select(self, *_args, **_kwargs): return [{"role": "analyst"}]

class AuthRoleTests(unittest.TestCase):
    def test_supabase_auth_gateway_builds_urllib_request(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self): return b'{"id":"user-1","email":"user@test"}'

        with patch("auth.dependencies.urlopen", return_value=Response()) as opener:
            gateway = SupabaseAuthGateway("http://supabase.test", "anon-key", FakeClient())
            self.assertEqual(gateway.user("access-token"), {"id": "user-1", "email": "user@test"})
            request = opener.call_args.args[0]
            self.assertEqual(request.full_url, "http://supabase.test/auth/v1/user")

    def test_viewer_is_denied_analyst_action(self):
        with self.assertRaises(HTTPException) as raised: require_roles("analyst")(Principal("u", "a@b.test", "viewer", False))
        self.assertEqual(raised.exception.status_code, 403)
    def test_password_change_flag_blocks_privileged_action(self):
        with self.assertRaises(HTTPException) as raised: require_roles("admin")(Principal("u", "a@b.test", "admin", True))
        self.assertEqual(raised.exception.detail, {"code": "INITIAL_PASSWORD_CHANGE_REQUIRED"})
    def test_admin_service_creates_profile_with_initial_password_flag(self):
        client = FakeClient(); user = UserService(client).create_user("new@fieldnote.test", "safe-temporary-password", "analyst")
        self.assertEqual(client.created[1], "users")
        self.assertEqual(client.profile, ("profiles", {"id": "user-1", "role": "analyst", "must_change_password": True}, "id"))
        self.assertTrue(user["must_change_password"])
    def test_password_is_changed_before_profile_flag_is_cleared(self):
        client = FakeClient(); UserService(client).change_password("user-1", "safe-new-password")
        self.assertEqual(client.created, ("PUT", "users/user-1", {"password": "safe-new-password"}))
        self.assertFalse(client.profile[1]["must_change_password"])
    def test_http_matrix_covers_anon_roles_and_initial_password_gate(self):
        principals = {
            "viewer": Principal("v", "v@test", "viewer", False),
            "analyst": Principal("a", "a@test", "analyst", False),
            "admin": Principal("d", "d@test", "admin", False),
            "initial": Principal("i", "i@test", "viewer", True),
        }
        class Gateway:
            def principal(self, token): return principals[token]
        with patch.object(api, "DATA_MODE", "supabase"), patch.object(api, "get_gateway", return_value=Gateway()):
            client = TestClient(api.app)
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(client.get("/api/categories").status_code, 401)
            for token in ("viewer", "analyst", "admin"):
                self.assertEqual(client.get("/api/categories", headers={"Authorization": f"Bearer {token}"}).status_code, 200)
            self.assertEqual(client.get("/api/categories", headers={"Authorization": "Bearer initial"}).status_code, 403)
            self.assertEqual(client.post("/api/research/preview", headers={"Authorization": "Bearer viewer"}, json={}).status_code, 403)

    def test_local_frontend_ports_are_allowed_by_api_cors(self):
        client = TestClient(api.app)
        for origin in ("http://127.0.0.1:3000", "http://localhost:3000", "http://127.0.0.1:5173"):
            response = client.options(
                "/api/health",
                headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
            )
            self.assertEqual(response.headers.get("access-control-allow-origin"), origin)

if __name__ == "__main__": unittest.main()
