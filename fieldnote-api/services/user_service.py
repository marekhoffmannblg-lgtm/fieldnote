from __future__ import annotations
from typing import Any
from auth.roles import Role
from repositories.supabase_client import SupabaseClient

class UserService:
    def __init__(self, client: SupabaseClient) -> None: self.client = client
    def create_user(self, email: str, password: str, role: Role) -> dict[str, Any]:
        user = self.client.auth_admin("POST", "users", {"email": email, "password": password, "email_confirm": True})
        user_id = str(user.get("id", ""))
        if not user_id: raise RuntimeError("Auth user creation failed.")
        self.client.upsert("profiles", {"id": user_id, "role": role, "must_change_password": True}, "id")
        return {"id": user_id, "email": email, "role": role, "must_change_password": True}
    def list_users(self) -> list[dict[str, Any]]: return self.client.select("profiles", select="id,role,must_change_password")
    def change_password(self, user_id: str, password: str) -> None:
        self.client.auth_admin("PUT", f"users/{user_id}", {"password": password})
        rows = self.client.select("profiles", select="role", id=f"eq.{user_id}")
        if not rows: raise RuntimeError("User profile is missing.")
        self.client.upsert("profiles", {"id": user_id, "role": rows[0]["role"], "must_change_password": False}, "id")
    def set_role(self, user_id: str, role: Role) -> None:
        self.client.upsert("profiles", {"id": user_id, "role": role}, "id")
