from __future__ import annotations
import json
import os
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from auth.roles import Principal, Role
from repositories.supabase_client import SupabaseClient, SupabaseConfigurationError

bearer = HTTPBearer(auto_error=False)

class SupabaseAuthGateway:
    def __init__(self, url: str, anon_key: str, client: SupabaseClient) -> None:
        if not url or not anon_key: raise SupabaseConfigurationError("Supabase Auth configuration is required.")
        self.url, self.anon_key, self.client = url.rstrip("/"), anon_key, client
    @classmethod
    def from_env(cls) -> "SupabaseAuthGateway":
        return cls(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_ANON_KEY", ""), SupabaseClient.from_env())
    def user(self, token: str) -> dict[str, Any]:
        request = Request(f"{self.url}/auth/v1/user", headers={"apikey": self.anon_key, "Authorization": f"Bearer {token}"})
        try:
            with urlopen(request, timeout=5) as response: value = json.loads(response.read().decode())
        except HTTPError as exc: raise HTTPException(status_code=401, detail="Nieprawidłowa sesja.") from exc
        if not isinstance(value, dict) or not value.get("id"): raise HTTPException(status_code=401, detail="Nieprawidłowa sesja.")
        return value
    def principal(self, token: str) -> Principal:
        user = self.user(token); rows = self.client.select("profiles", select="id,role,must_change_password", id=f"eq.{user['id']}")
        if not rows or rows[0].get("role") not in {"viewer", "analyst", "admin"}: raise HTTPException(status_code=403, detail="Brak uprawnień profilu.")
        profile = rows[0]
        return Principal(str(user["id"]), str(user.get("email", "")), profile["role"], bool(profile.get("must_change_password", True)))

def get_gateway() -> SupabaseAuthGateway: return SupabaseAuthGateway.from_env()
def current_principal(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    cached = getattr(request.state, "principal", None)
    if isinstance(cached, Principal): return cached
    if credentials is None or credentials.scheme.lower() != "bearer": raise HTTPException(status_code=401, detail="Wymagane logowanie.")
    return get_gateway().principal(credentials.credentials)
def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.must_change_password: raise HTTPException(status_code=403, detail={"code": "INITIAL_PASSWORD_CHANGE_REQUIRED"})
        if principal.role not in roles: raise HTTPException(status_code=403, detail="Brak uprawnień.")
        return principal
    return dependency

def require_data_write(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    """Keep the legacy-local API behaviour until Supabase mode is explicitly enabled."""
    if os.getenv("FIELDNOTE_DATA_MODE", "legacy_readonly") == "legacy_readonly":
        return Principal("legacy-local", "", "admin", False)
    if credentials is None or credentials.scheme.lower() != "bearer": raise HTTPException(status_code=401, detail="Wymagane logowanie.")
    principal = get_gateway().principal(credentials.credentials)
    if principal.must_change_password: raise HTTPException(status_code=403, detail={"code": "INITIAL_PASSWORD_CHANGE_REQUIRED"})
    if principal.role not in {"analyst", "admin"}: raise HTTPException(status_code=403, detail="Brak uprawnień.")
    return principal
