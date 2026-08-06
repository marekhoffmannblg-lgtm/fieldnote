from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth.dependencies import require_data_write
from auth.roles import Principal
from services.job_service import DuplicateActiveJobError, JobNotFoundError, JobNotRetryableError, JobService


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobLimitsRequest(BaseModel):
    max_pages: int = Field(default=10, ge=1, le=100)
    max_ai_tokens: int = Field(default=20_000, ge=1, le=2_000_000)
    timeout_seconds: int = Field(default=900, ge=1, le=7_200)
    max_retries: int = Field(default=1, ge=1, le=5)


class CreateResearchJobRequest(BaseModel):
    product_slug: str = Field(min_length=3, max_length=160, pattern=r"^[a-z0-9]+__[a-z0-9-]+$")
    limits: JobLimitsRequest = Field(default_factory=JobLimitsRequest)
    selected_offer_ids: list[str] = Field(default_factory=list, max_length=100)
    selected_manufacturer_source_ids: list[str] = Field(default_factory=list, max_length=100)
    include_manufacturer_sources: bool = False
    skip_ai: bool = False
    cost_limit: float | None = Field(default=None, ge=0, le=1_000_000)


class CreateProductRefreshJobRequest(BaseModel):
    product_slug: str = Field(min_length=3, max_length=160, pattern=r"^[a-z0-9]+__[a-z0-9-]+$")
    limits: JobLimitsRequest = Field(default_factory=JobLimitsRequest)
    cost_limit: float | None = Field(default=None, ge=0, le=1_000_000)


def get_service(request: Request) -> JobService:
    service = getattr(request.app.state, "job_service", None)
    if not isinstance(service, JobService):
        raise HTTPException(status_code=503, detail="Kolejka PostgreSQL nie jest skonfigurowana.")
    return service


def public_job(job: dict[str, Any], *, include_events: bool = False) -> dict[str, Any]:
    """Expose the durable database job through the existing run-shaped UI contract."""
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    usage = job.get("usage") if isinstance(job.get("usage"), dict) else {}
    status = str(job.get("status", "queued"))
    response: dict[str, Any] = {
        "run_id": str(job.get("job_id", "")), "job_id": str(job.get("job_id", "")),
        "product_slug": str(payload.get("product_slug", "")),
        "brand": str(payload.get("brand", "")), "model": str(payload.get("model", "")),
        "status": status,
        "current_step": {"queued": "W kolejce", "leased": "Przydzielono workerowi", "running": "W toku"}.get(status, "Zakończono"),
        "progress": 100 if status in {"succeeded", "partial", "failed", "cancelled"} else 0,
        "started_at": job.get("started_at"), "finished_at": job.get("completed_at"),
        "created_at": job.get("requested_at"), "cost_limit": job.get("cost_limit"),
        "cost_used": job.get("cost_used"),
        "logs_tail": [str(result.get("output_tail", ""))] if result.get("output_tail") else [],
        "usage": usage, "snapshot_updated": bool(result.get("snapshot_updated", False)),
        "error": result.get("error") or job.get("error") or "",
        "retry_of": payload.get("retry_of") or result.get("retry_of"),
        "sources_selected": result.get("sources_selected", usage.get("sources_selected")),
        "coverage_before": result.get("coverage_before"),
        "coverage_after": result.get("coverage_after"),
    }
    if include_events:
        response["events"] = job.get("events", [])
    return response


@router.post("/research", status_code=202)
def create_research_job(body: CreateResearchJobRequest, principal: Principal = Depends(require_data_write), service: JobService = Depends(get_service)) -> dict[str, Any]:
    try:
        job = service.enqueue(product_slug=body.product_slug, requested_by=principal.user_id, limits=body.limits.model_dump(), selection={"selected_offer_ids": body.selected_offer_ids, "selected_manufacturer_source_ids": body.selected_manufacturer_source_ids, "include_manufacturer_sources": body.include_manufacturer_sources, "skip_ai": body.skip_ai}, cost_limit=body.cost_limit)
    except DuplicateActiveJobError as exc:
        raise HTTPException(status_code=409, detail="Dla tego produktu działa już aktywne zadanie researchu.") from exc
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Nie znaleziono produktu.") from exc
    return public_job(job)


@router.post("/product-refresh", status_code=202)
def create_product_refresh_job(body: CreateProductRefreshJobRequest, principal: Principal = Depends(require_data_write), service: JobService = Depends(get_service)) -> dict[str, Any]:
    """Queue exactly one fresh product refresh; execution belongs to worker."""
    try:
        job = service.enqueue(product_slug=body.product_slug, requested_by=principal.user_id,
                              limits=body.limits.model_dump(), selection={"refresh": True},
                              cost_limit=body.cost_limit, job_type="product_refresh")
    except DuplicateActiveJobError as exc:
        raise HTTPException(status_code=409, detail="Dla tego produktu działa już aktywne zadanie.") from exc
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Nie znaleziono produktu.") from exc
    return public_job(job)


@router.get("")
def list_jobs(limit: int = 50, offset: int = 0, service: JobService = Depends(get_service)) -> dict[str, Any]:
    jobs = service.list(limit=limit, offset=offset)
    runs = [public_job(job) for job in jobs]
    safe_limit, safe_offset = min(max(limit, 1), 200), max(offset, 0)
    return {"items": runs, "runs": runs, "total": service.count(), "limit": safe_limit, "offset": safe_offset}


@router.get("/{job_id}")
def job_detail(job_id: str, service: JobService = Depends(get_service)) -> dict[str, Any]:
    try: return public_job(service.detail(job_id), include_events=True)
    except JobNotFoundError as exc: raise HTTPException(status_code=404, detail="Nie znaleziono zadania.") from exc


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, _: Principal = Depends(require_data_write), service: JobService = Depends(get_service)) -> dict[str, Any]:
    try: return public_job(service.cancel(job_id))
    except JobNotFoundError as exc: raise HTTPException(status_code=404, detail="Nie znaleziono zadania.") from exc


@router.post("/{job_id}/retry", status_code=202)
def retry_job(job_id: str, principal: Principal = Depends(require_data_write), service: JobService = Depends(get_service)) -> dict[str, Any]:
    try:
        return public_job(service.retry(job_id, requested_by=principal.user_id))
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Nie znaleziono zadania.") from exc
    except JobNotRetryableError as exc:
        raise HTTPException(status_code=409, detail="To zadanie nie może zostać ponowione.") from exc
    except DuplicateActiveJobError as exc:
        raise HTTPException(status_code=409, detail="Dla tego produktu działa już aktywne zadanie researchu.") from exc
