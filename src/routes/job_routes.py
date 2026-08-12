from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from src.middleware.auth import require_auth
from src.middleware.quota import check_job_quota
from src.schemas.fe_contract import (
    CreateJobRequest,
    CreateJobResponse,
    JobProgress,
    JobSummary,
)
from src.services import job_service, stubs

router = APIRouter(tags=["jobs"], dependencies=[Depends(require_auth)])


@router.post(
    "/jobs",
    response_model=CreateJobResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_job_quota)],
)
async def create_job(
    req: CreateJobRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> CreateJobResponse:
    """Create a new training job and immediately start the pre-masking stub.

    Quota is checked before the job is created (check_job_quota dependency).
    owner_id is read from request.state (set by require_auth) and stored on
    the job document so quota and ownership queries work correctly.
    The pre_masking background task sleeps 4 s then advances the job stage
    to awaiting_annotation.  The HTTP response (201) is returned instantly —
    the client polls GET /jobs/{id} to follow stage progression.
    """
    owner_id: str = getattr(request.state, "user_id", "")
    result = job_service.create_job(req, owner_id=owner_id)
    background_tasks.add_task(stubs.run_pre_masking, result.job_id)
    return result


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
