from __future__ import annotations
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from auth.dependencies import require_roles
from auth.roles import Principal, Role
from services.user_service import UserService
from repositories.supabase_client import SupabaseClient
router = APIRouter(prefix="/api/admin/users", tags=["admin"])
class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    temporary_password: str = Field(min_length=12)
    role: Role = "viewer"
def get_users() -> UserService: return UserService(SupabaseClient.from_env())
@router.get("")
def list_users(_: Principal = Depends(require_roles("admin")), service: UserService = Depends(get_users)) -> dict[str, object]: return {"items": service.list_users()}
@router.post("")
def create_user(request: CreateUserRequest, _: Principal = Depends(require_roles("admin")), service: UserService = Depends(get_users)) -> dict[str, object]: return service.create_user(request.email, request.temporary_password, request.role)
