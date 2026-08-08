"""Ingestion job status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import JobOut
from app.storage import job_repo

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str) -> JobOut:
    """Return the status of a single ingestion job; 404 if unknown."""
    job = await job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobOut(**job)
