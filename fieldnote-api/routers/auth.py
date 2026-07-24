from __future__ import annotations
from fastapi import APIRouter, Depends
from auth.dependencies import current_principal
from auth.roles import Principal
from repositories.supabase_client import SupabaseClient
router = APIRouter(prefix="/api/auth", tags=["auth"])
@router.get("/me")
def me(principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return {"user_id": principal.user_id, "email": principal.email, "role": principal.role, "must_change_password": principal.must_change_password}

@router.post("/change-password")
def change_password(principal: Principal = Depends(current_principal)) -> dict[str, bool]:
    """Called only after Supabase Auth has changed the user's password."""
    SupabaseClient.from_env().upsert("profiles", {"id": principal.user_id, "role": principal.role, "must_change_password": False}, "id")
    return {"must_change_password": False}
