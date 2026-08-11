from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.middleware.auth import require_auth
from src.schemas.fe_contract import (
    AnnotationsRequest,
    AnnotationsResponse,
    ApproveResponse,
    RejectResponse,
    RerunResponse,
)
from src.services import job_service, stubs

router = APIRouter(tags=["job-actions"], dependencies=[Depends(require_auth)])

# ── Shared error helpers ──────────────────────────────────────────────────────


def _not_found(job_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"job {job_id} not found",
    )


def _wrong_stage(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


# ── POST /jobs/{job_id}/annotations ──────────────────────────────────────────


@router.post("/jobs/{job_id}/annotations", response_model=AnnotationsResponse)
async def submit_annotations(
    job_id: str,
    body: AnnotationsRequest,
) -> AnnotationsResponse:
    """Accept the annotation upload acknowledgement and advance to awaiting_approval.

    The FE sends { "ack": true } (JSON body).  No real COCO zip is processed in V1.
    Guard: job must be in awaiting_annotation — returns 409 otherwise.
    """
    try:
        return job_service.submit_annotations(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _wrong_stage(str(exc)) from exc


# ── POST /jobs/{job_id}/approve ───────────────────────────────────────────────


@router.post("/jobs/{job_id}/approve", response_model=ApproveResponse)
async def approve_job(
    job_id: str,
    background_tasks: BackgroundTasks,
) -> ApproveResponse:
    """Approve a job awaiting human review → advance to training.

    Immediately spawns the training stub as a BackgroundTask.
    Guard: job must be in awaiting_approval — returns 409 otherwise.
    """
    try:
        result = job_service.approve_job(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _wrong_stage(str(exc)) from exc

    background_tasks.add_task(stubs.run_training, job_id)
    return result


# ── POST /jobs/{job_id}/reject ────────────────────────────────────────────────


@router.post("/jobs/{job_id}/reject", response_model=RejectResponse)
async def reject_job(job_id: str) -> RejectResponse:
    """Reject a job awaiting human review → terminate it permanently.

    Guard: job must be in awaiting_approval — returns 409 otherwise.
    """
    try:
        return job_service.reject_job(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _wrong_stage(str(exc)) from exc


# ── POST /jobs/{job_id}/rerun ─────────────────────────────────────────────────


@router.post("/jobs/{job_id}/rerun", response_model=RerunResponse)
async def rerun_job(
    job_id: str,
    background_tasks: BackgroundTasks,
) -> RerunResponse:
    """Clone a finished job and start it from scratch.

    Copies the original prompt + dataset_object_path into a new job document,
    then immediately spawns the pre_masking background task for the new job.
    Guard: original job must be in a terminal stage (done | rejected | error | failed).
    """
    try:
        result = job_service.rerun_job(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _wrong_stage(str(exc)) from exc

    background_tasks.add_task(stubs.run_pre_masking, result.new_job_id)
    return result
