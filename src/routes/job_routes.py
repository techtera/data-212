from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.middleware.auth import require_auth
from src.schemas.fe_contract import (
    CreateJobRequest,
    CreateJobResponse,
    JobProgress,
    JobSummary,
)
from src.services import job_service

router = APIRouter(tags=["jobs"], dependencies=[Depends(require_auth)])


@router.post("/jobs", response_model=CreateJobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(req: CreateJobRequest) -> CreateJobResponse:
    """Create a new training job.

    Validates the request, writes to Firestore, and returns the job_id + initial stage.
    Spawning the pre_masking background task is wired in M3.
    """
    return job_service.create_job(req)


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs() -> list[JobSummary]:
    """Return all jobs ordered by Firestore insertion order (newest last)."""
    return job_service.list_jobs()


@router.get("/jobs/{job_id}", response_model=JobProgress)
async def get_job(job_id: str) -> JobProgress:
    """Return the current progress snapshot for a single job.

    Raises 404 if the job_id is not found in Firestore.
    """
    progress = job_service.get_job_progress(job_id)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    return progress
