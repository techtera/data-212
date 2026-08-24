"""Job routes - create, list, run, and retrieve results for eval/finetune jobs."""

import json
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import require_auth
from .db import execute, fetch_all, fetch_one
from .gcs import mint_signed_get_url
from .models import get_model_by_name, get_model_by_name_async
from .training import run_eval, run_finetune

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateJobRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    epochs: int | None = None
    lr: float | None = None


class JobResponse(BaseModel):
    id: str
    name: str | None = None
    job_type: str
    status: str
    model_name: str
    error_message: str | None = None
    created_at: str
    updated_at: str


class ResultsResponse(BaseModel):
    id: str
    status: str
    job_type: str = "eval"
    prediction_urls: list[str] = []
    mean_iou: float = 0
    dice_score: float = 0
    pixel_accuracy: float = 0
    artifacts: dict | None = None


class DownloadResponse(BaseModel):
    checkpoint_url: str | None = None
    inference_script_url: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_response(row) -> JobResponse:
    return JobResponse(
        id=str(row["id"]),
        name=row["name"],
        job_type=row["job_type"],
        status=row["status"],
        model_name=row["model_id"],
        error_message=row["error_message"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )


async def _get_owned_job(job_id: str, user_id: UUID):
    """Fetch a job and verify ownership."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = await fetch_one("SELECT * FROM jobs WHERE id = $1", job_uuid)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["owner_id"] != user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[JobResponse])
async def list_jobs(user_id: UUID = Depends(require_auth)):
    """List all jobs for the current user."""
    rows = await fetch_all(
        "SELECT * FROM jobs WHERE owner_id = $1 ORDER BY created_at DESC",
        user_id,
    )
    return [_job_response(row) for row in rows]


@router.post("/eval", response_model=JobResponse, status_code=201)
async def create_eval_job(body: CreateJobRequest, user_id: UUID = Depends(require_auth)):
    """Create a new evaluation/inference job."""
    model = await get_model_by_name_async(body.model_name, str(user_id))
    if not model:
        raise HTTPException(status_code=400, detail=f"Unknown model: {body.model_name}")

    job_name = body.name
    gcs_images = f"upload/{user_id}/{job_name}/images.zip"
    gcs_masks = f"upload/{user_id}/{job_name}/masks.zip"

    row = await fetch_one(
        """INSERT INTO jobs (owner_id, name, job_type, status, model_id, dataset_id, gcs_images_zip, gcs_masks_zip)
           VALUES ($1, $2, 'eval', 'uploading', $3, $4, $5, $6)
           RETURNING *""",
        user_id,
        job_name,
        body.model_name,
        job_name,
        gcs_images,
        gcs_masks,
    )

    return _job_response(row)


@router.post("/finetune", response_model=JobResponse, status_code=201)
async def create_finetune_job(body: CreateJobRequest, user_id: UUID = Depends(require_auth)):
    """Create a new fine-tuning job."""
    model = await get_model_by_name_async(body.model_name, str(user_id))
    if not model:
        raise HTTPException(status_code=400, detail=f"Unknown model: {body.model_name}")

    job_name = body.name
    gcs_images = f"upload/{user_id}/{job_name}/images.zip"
    gcs_masks = f"upload/{user_id}/{job_name}/masks.zip"

    training_config = {}
    if body.epochs:
        training_config["epochs"] = body.epochs
    if body.lr:
        training_config["lr"] = body.lr

    row = await fetch_one(
        """INSERT INTO jobs (owner_id, name, job_type, status, model_id, dataset_id, gcs_images_zip, gcs_masks_zip, artifacts)
           VALUES ($1, $2, 'finetune', 'uploading', $3, $4, $5, $6, $7::jsonb)
           RETURNING *""",
        user_id,
        job_name,
        body.model_name,
        job_name,
        gcs_images,
        gcs_masks,
        json.dumps(training_config) if training_config else None,
    )

    return _job_response(row)


@router.post("/{job_id}/run-eval", response_model=JobResponse)
async def trigger_eval(
    job_id: str,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(require_auth),
):
    """Start evaluation for a job. Multiple jobs can run in parallel."""
    job = await _get_owned_job(job_id, user_id)

    if job["job_type"] != "eval":
        raise HTTPException(status_code=400, detail="Job is not an eval job")

    if job["status"] not in ("uploading",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start eval: job status is '{job['status']}' (expected 'uploading')",
        )

    await execute(
        "UPDATE jobs SET status = 'running', updated_at = NOW() WHERE id = $1",
        job["id"],
    )

    background_tasks.add_task(run_eval, str(job["id"]), job["model_id"], job["name"], str(job["owner_id"]))

    updated = await fetch_one("SELECT * FROM jobs WHERE id = $1", job["id"])
    return _job_response(updated)


@router.post("/{job_id}/run-finetune", response_model=JobResponse)
async def trigger_finetune(
    job_id: str,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(require_auth),
):
    """Start fine-tuning for a job. Multiple jobs can run in parallel."""
    job = await _get_owned_job(job_id, user_id)

    if job["job_type"] != "finetune":
        raise HTTPException(status_code=400, detail="Job is not a finetune job")

    if job["status"] not in ("uploading",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start finetune: job status is '{job['status']}' (expected 'uploading')",
        )

    await execute(
        "UPDATE jobs SET status = 'running', updated_at = NOW() WHERE id = $1",
        job["id"],
    )

    background_tasks.add_task(run_finetune, str(job["id"]), job["model_id"], job["name"], str(job["owner_id"]))

    updated = await fetch_one("SELECT * FROM jobs WHERE id = $1", job["id"])
    return _job_response(updated)


@router.get("/{job_id}/results", response_model=ResultsResponse)
async def get_results(job_id: str, user_id: UUID = Depends(require_auth)):
    """Get signed prediction image URLs for a completed job."""
    job = await _get_owned_job(job_id, user_id)

    prediction_urls = []
    if job["predictions"]:
        predictions = job["predictions"] if isinstance(job["predictions"], list) else json.loads(job["predictions"])
        for pred_path in predictions:
            url = mint_signed_get_url(pred_path)
            prediction_urls.append(url)

    artifacts = None
    if job["artifacts"]:
        artifacts = job["artifacts"] if isinstance(job["artifacts"], dict) else json.loads(job["artifacts"] or "{}")

    return ResultsResponse(
        id=str(job["id"]),
        status=job["status"],
        job_type=job["job_type"],
        prediction_urls=prediction_urls,
        mean_iou=job["mean_iou"] or 0,
        dice_score=job["dice_score"] or 0,
        pixel_accuracy=job["pixel_accuracy"] or 0,
        artifacts=artifacts,
    )


@router.get("/{job_id}/download", response_model=DownloadResponse)
async def get_download_urls(job_id: str, user_id: UUID = Depends(require_auth)):
    """Get signed download URLs for checkpoint and inference script."""
    job = await _get_owned_job(job_id, user_id)

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job is not yet complete")

    if job["job_type"] != "finetune":
        raise HTTPException(status_code=400, detail="Download only available for finetune jobs")

    artifacts = job["artifacts"] if isinstance(job["artifacts"], dict) else json.loads(job["artifacts"] or "{}")

    checkpoint_url = None
    script_url = None

    if "checkpoint" in artifacts:
        checkpoint_url = mint_signed_get_url(artifacts["checkpoint"])

    if "inference_script" in artifacts:
        script_url = mint_signed_get_url(artifacts["inference_script"])

    return DownloadResponse(
        checkpoint_url=checkpoint_url,
        inference_script_url=script_url,
    )
