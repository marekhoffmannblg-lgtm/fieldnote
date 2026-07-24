from __future__ import annotations
import sys
import unittest
from pathlib import Path
from fastapi import HTTPException
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))
from auth.dependencies import require_roles
from auth.roles import Principal
from services.user_service import UserService

class FakeClient:
    def __init__(self): self.created = None; self.profile = None
    def auth_admin(self, method, path, payload): self.created = (method, path, payload); return {"id": "user-1"}
    def upsert(self, table, payload, conflict): self.profile = (table, payload, conflict); return []
    def select(self, *_args, **_kwargs): return []

class AuthRoleTests(unittest.TestCase):
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

if __name__ == "__main__": unittest.main()
