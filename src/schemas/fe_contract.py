from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# ── Shapes that match the frontend TypeScript types exactly ───────────────────
# Field names must be identical to the TS interfaces in frontend/src/types/job.ts


class CreateJobRequest(BaseModel):
    """POST /jobs  —  matches FE CreateJobRequest."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "prompt": "train a segmentation model on my dataset",
                    "dataset_object_path": "datasets/ds_abc123/raw.zip",
                }
            ]
        }
    )

    prompt: str
    dataset_object_path: str


class CreateJobResponse(BaseModel):
    """POST /jobs  →  matches FE CreateJobResponse."""

    job_id: str
    stage: str  # Stage string, e.g. "pre_masking"


class JobSummary(BaseModel):
    """GET /jobs  →  matches FE JobSummary (one element of the list)."""

    job_id: str
    prompt: str
    stage: str
    risk_tier: str | None = None
    created_at: str  # ISO 8601 string


class JobProgress(BaseModel):
    """GET /jobs/{id}  →  matches FE JobProgress."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "stage": "pre_masking",
                    "progress": 25,
                }
            ]
        }
    )

    stage: str
    progress: int  # 0-100
    flagged: list[dict] | None = None  # list[FlaggedImage]
    unannotated_count: int | None = None
    annotated_count: int | None = None
    epoch: int | None = None
    total_epochs: int | None = None
    stage_failed: str | None = None
    log_excerpt: str | None = None
