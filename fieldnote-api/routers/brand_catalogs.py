from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.dependencies import require_roles
from auth.roles import Principal
from services.brand_catalog_service import BrandCatalogService


router = APIRouter(prefix="/api/brand-catalogs", tags=["brand-catalogs"])


class CatalogRefreshRequest(BaseModel):
    brand: str = Field(min_length=1, max_length=80)
    fixture_root: str | None = None


def get_service() -> BrandCatalogService:
    return BrandCatalogService()


@router.get("")
def list_brand_catalogs(brand: str | None = None, service: BrandCatalogService = Depends(get_service)) -> dict[str, Any]:
    return service.current(brand)


@router.post("/discover", status_code=202)
def discover_brand_catalog(request: CatalogRefreshRequest, _: Principal = Depends(require_roles("admin")), service: BrandCatalogService = Depends(get_service)) -> dict[str, Any]:
    fixture = Path(request.fixture_root).resolve() if request.fixture_root else None
    if fixture is not None and not fixture.exists():
        raise HTTPException(status_code=422, detail="Fixture katalogu nie istnieje.")
    # Preview only: committing catalog rows belongs to the later import unit.
    return service.discover(request.brand, fixture_root=fixture)
