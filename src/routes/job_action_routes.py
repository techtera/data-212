from __future__ import annotations

import logging

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
from src.services.gcs_service import GCSServiceError, mint_signed_get_url, mint_signed_put_url
from src.services.jwt_hop import issue_hop_token

logger = logging.getLogger(__name__)

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
    """Accept the annotation upload acknowledgement and advance to researching.

    The FE sends { "ack": true } (JSON body).  No real COCO zip is processed in V1.
    Guard: job must be in awaiting_annotation — returns 409 otherwise.

    V4: After advancing to researching, a research-scoped hop token is minted
    and the research task is dispatched via the broker. The research agent will
    call Gemini, score risk, and advance the job to awaiting_approval.
    """
    try:
        result = job_service.submit_annotations(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _wrong_stage(str(exc)) from exc

    # Dispatch research task via broker with a research-scoped hop token
    token = issue_hop_token(job_id, step="research")
    broker = get_broker()
    await broker.enqueue(BrokerTask(job_id=job_id, task_type="research", hop_token=token))
    return result


# ── POST /jobs/{job_id}/approve ───────────────────────────────────────────────


@router.post("/jobs/{job_id}/approve", response_model=ApproveResponse)
async def approve_job(job_id: str) -> ApproveResponse:
    """Approve a job awaiting human review → advance to training.

    Mints a training-scoped hop token and dispatches the training task
    via the broker. Also mints time-boxed GCS signed URLs for the training
    agent to fetch data and upload results (V4-GCS-M2).

    Guard: job must be in awaiting_approval — returns 409 otherwise.
    """
    try:
        result = job_service.approve_job(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _wrong_stage(str(exc)) from exc

    # Mint GCS signed URLs for the training agent
    training_payload: dict = {}  # type: ignore[type-arg]
    try:
        dataset_path = job_service.get_job_dataset_path(job_id)
        if dataset_path:
            training_payload["dataset_signed_url"] = mint_signed_get_url(dataset_path)
            training_payload["weights_signed_url"] = mint_signed_get_url("weights/base.pt")
            training_payload["results_upload_url"] = mint_signed_put_url(
                f"results/{job_id}/best.pt",
                content_type="application/octet-stream",
            )
            training_payload["results_metrics_url"] = mint_signed_put_url(
                f"results/{job_id}/metrics.json",
                content_type="application/json",
            )
            logger.info("Job %s: minted training GCS signed URLs", job_id)
    except GCSServiceError as exc:
        # Log but don't block training — stubs don't use URLs yet.
        # In V4-VERTEX this will become a hard failure.
        logger.warning("Job %s: GCS URL minting failed (non-fatal for stubs): %s", job_id, exc)

    token = issue_hop_token(job_id, step="training")
    broker = get_broker()
    await broker.enqueue(
        BrokerTask(job_id=job_id, task_type="training", hop_token=token, payload=training_payload)
    )
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
