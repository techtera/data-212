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


# ── M4 action response shapes ─────────────────────────────────────────────────


class AnnotationsRequest(BaseModel):
    """POST /jobs/{id}/annotations  —  FE sends { ack: true } in V1.

    In V4 this will be replaced with multipart/form-data carrying the COCO zip.
    """

    ack: bool = True


class AnnotationsResponse(BaseModel):
    """POST /jobs/{id}/annotations  →  matches FE AnnotationsResponse."""

    ok: bool
    stage: str  # "awaiting_approval"


class ApproveResponse(BaseModel):
    """POST /jobs/{id}/approve  →  matches FE ApproveResponse."""

    stage: str  # "training"


class RejectResponse(BaseModel):
    """POST /jobs/{id}/reject  →  matches FE RejectResponse."""

    stage: str  # "rejected"


class RerunResponse(BaseModel):
    """POST /jobs/{id}/rerun  →  matches FE RerunResponse."""

    new_job_id: str
    stage: str  # "pre_masking"


# ── M5 data / upload / auth response shapes ───────────────────────────────────


class UploadSignResponse(BaseModel):
    """POST /uploads/sign  →  matches FE UploadSignResponse."""

    signed_put_url: str  # GCS signed PUT URL (V4) or stub path (V1)
    object_path: str  # "datasets/{id}/raw.zip"


class LoginRequest(BaseModel):
    """POST /auth/login  —  hardcoded V1 username/password check."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """POST /auth/login  →  token + expiry for V1 static auth."""

    token: str
    expires_at: str  # ISO 8601 — far future in V1


class FlaggedImage(BaseModel):
    """One element of GET /jobs/{id}/flagged  →  matches FE FlaggedImage."""

    image_id: str
    url: str


class DataPreviewImage(BaseModel):
    """One element of GET /jobs/{id}/data-preview  →  matches FE DataPreviewImage."""

    image_id: str
    url: str


class ComputeSample(BaseModel):
    """GET /jobs/{id}/compute  →  matches FE ComputeSample."""

    vram_used_mb: float
    vram_total_mb: float
    gpu_util_pct: float
    quota_remaining_jobs: int
    quota_remaining_minutes: int
    ts: str  # ISO 8601 server timestamp


class LogLine(BaseModel):
    """One log line inside LogsResponse  →  matches FE LogLine."""

    ts: str
    level: str  # "info" | "warn" | "error"
    msg: str


class EpochMetrics(BaseModel):
    """One epoch row inside LogsResponse  →  matches FE EpochMetrics."""

    epoch: int
    loss_tr: float
    loss_val: float
    acc: float
    iou: float
    dice: float


class LogsResponse(BaseModel):
    """GET /jobs/{id}/logs  →  matches FE LogsResponse."""

    lines: list[LogLine]
    epochs: list[EpochMetrics]


class FinalMetrics(BaseModel):
    """Nested in ResultsResponse  →  matches FE FinalMetrics."""

    loss_val: float
    acc: float
    iou: float
    dice: float
    epochs: int
    total_minutes: float


class SamplePrediction(BaseModel):
    """One prediction triplet in ResultsResponse  →  matches FE SamplePrediction."""

    image_url: str
    pred_mask_url: str
    gt_mask_url: str


class ResultsResponse(BaseModel):
    """GET /jobs/{id}/results  →  matches FE ResultsResponse."""

    final_metrics: FinalMetrics
    sample_predictions: list[SamplePrediction]
    risk_tier: str  # "low" | "medium" | "high" | "auto"
    risk_reasoning: str


class InferenceResponse(BaseModel):
    """GET /jobs/{id}/inference  →  matches FE InferenceResponse."""

    code: str
    checkpoint_signed_url: str
