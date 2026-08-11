from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.middleware.auth import require_auth
from src.schemas.fe_contract import (
    ComputeSample,
    DataPreviewImage,
    FlaggedImage,
    InferenceResponse,
    LogsResponse,
    ResultsResponse,
)
from src.services import data_service

router = APIRouter(tags=["job-data"], dependencies=[Depends(require_auth)])


def _not_found(job_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"job {job_id} not found",
    )


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.get("/jobs/{job_id}/flagged", response_model=list[FlaggedImage])
async def get_flagged(job_id: str) -> list[FlaggedImage]:
    """Return the low-confidence flagged images for annotation.

    Only meaningful during stage=awaiting_annotation; the list is canned in V1.
    """
    try:
        return data_service.get_flagged(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc


@router.get("/jobs/{job_id}/data-preview", response_model=list[DataPreviewImage])
async def get_data_preview(job_id: str) -> list[DataPreviewImage]:
    """Return 32 random dataset-preview images (image-only, no masks)."""
    try:
        return data_service.get_data_preview(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc


@router.get("/jobs/{job_id}/compute", response_model=ComputeSample)
async def get_compute(job_id: str) -> ComputeSample:
    """Return live VRAM / GPU / quota stats for the job."""
    try:
        return data_service.get_compute(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc


@router.get("/jobs/{job_id}/logs", response_model=LogsResponse)
async def get_logs(job_id: str) -> LogsResponse:
    """Return accumulated epoch metrics and log lines for the job."""
    try:
        return data_service.get_logs(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc


@router.get("/jobs/{job_id}/results", response_model=ResultsResponse)
async def get_results(job_id: str) -> ResultsResponse:
    """Return final training results.  Only available when stage=done (409 otherwise)."""
    try:
        return data_service.get_results(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _conflict(str(exc)) from exc


@router.get("/jobs/{job_id}/inference", response_model=InferenceResponse)
async def get_inference(job_id: str) -> InferenceResponse:
    """Return the inference script and checkpoint URL.  Only available when stage=done."""
    try:
        return data_service.get_inference(job_id)
    except KeyError as exc:
        raise _not_found(job_id) from exc
    except ValueError as exc:
        raise _conflict(str(exc)) from exc
