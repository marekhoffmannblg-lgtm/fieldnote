from __future__ import annotations
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from auth.dependencies import current_principal
from auth.roles import Principal
from services.user_service import UserService
from repositories.supabase_client import SupabaseClient
router = APIRouter(prefix="/api/auth", tags=["auth"])
@router.get("/me")
def me(principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return {"user_id": principal.user_id, "email": principal.email, "role": principal.role, "must_change_password": principal.must_change_password}

class ChangePasswordRequest(BaseModel): password: str = Field(min_length=12)
def get_users() -> UserService: return UserService(SupabaseClient.from_env())
@router.post("/change-password")
def change_password(request: ChangePasswordRequest, principal: Principal = Depends(current_principal), service: UserService = Depends(get_users)) -> dict[str, bool]:
    service.change_password(principal.user_id, request.password)
    return {"must_change_password": False}
