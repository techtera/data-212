from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.middleware.auth import require_auth
from src.schemas.fe_contract import (
    AnnotationsRequest,
    AnnotationsResponse,
    ApproveResponse,
    RejectResponse,
    RerunResponse,
)
from src.services import job_service
from src.services.broker import BrokerTask, get_broker
from src.services.jwt_hop import issue_hop_token

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
async def approve_job(job_id: str) -> ApproveResponse:
    """Approve a job awaiting human review → advance to training.

    Mints a training-scoped hop token and dispatches the training task
    via the broker.
    Guard: job must be in awaiting_approval — returns 409 otherwise.
    """
    try:
        result = job_service.approve_job(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _wrong_stage(str(exc)) from exc

    token = issue_hop_token(job_id, step="training")
    broker = get_broker()
    await broker.enqueue(BrokerTask(job_id=job_id, task_type="training", hop_token=token))
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
async def rerun_job(job_id: str) -> RerunResponse:
    """Clone a finished job and start it from scratch.

    Copies the original prompt + dataset_object_path into a new job document,
    mints a pre_masking hop token and dispatches via the broker.
    Guard: original job must be in a terminal stage (done | rejected | error | failed).
    """
    try:
        result = job_service.rerun_job(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _wrong_stage(str(exc)) from exc

    token = issue_hop_token(result.new_job_id, step="pre_masking")
    broker = get_broker()
    await broker.enqueue(
        BrokerTask(job_id=result.new_job_id, task_type="pre_masking", hop_token=token)
    )
    return result
