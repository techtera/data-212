from __future__ import annotations

import logging

from src.db.crud import create_doc, get_doc, query_docs
from src.db.firebase import db  # noqa: F401  (imported to ensure Firebase is initialised)
from src.schemas.fe_contract import (
    CreateJobRequest,
    CreateJobResponse,
    JobProgress,
    JobSummary,
)
from src.schemas.job import JobStatus

logger = logging.getLogger(__name__)

COLLECTION = "jobs"

# ── Canned flagged images (V1 stub — replaced in M5 with real data) ────────────
_CANNED_FLAGGED = [
    {"image_id": "9", "url": "/mock-data/flagged/9.png"},
    {"image_id": "10", "url": "/mock-data/flagged/10.png"},
    {"image_id": "11", "url": "/mock-data/flagged/11.png"},
    {"image_id": "12", "url": "/mock-data/flagged/12.png"},
]


def _compute_progress(stage: str, epoch: int | None, total_epochs: int | None) -> int:
    """Derive the 0-100 progress integer from the current stage.

    Matches the logic in the MSW mock so the FE progress bar behaves identically.
    """
    match stage:
        case "pre_masking":
            return 25
        case "awaiting_annotation":
            return 50
        case "awaiting_approval":
            return 75
        case "training":
            ep = epoch or 0
            tot = total_epochs or 10
            return round(ep / tot * 100) if tot else 0
        case "done":
            return 100
        case _:  # rejected, error, failed
            return 0


def create_job(req: CreateJobRequest) -> CreateJobResponse:
    """Write a new job document and return the FE-facing CreateJobResponse.

    Maps FE fields (prompt, dataset_object_path) → Firestore document.
    Status is always forced to pre_masking on creation.
    """

    from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore[import-untyped]

    payload = {
        "prompt": req.prompt,
        "dataset_object_path": req.dataset_object_path,
        "status": JobStatus.pre_masking.value,
        "risk_tier": None,
        "epoch": None,
        "total_epochs": 10,
        "flagged_images": _CANNED_FLAGGED,
        "unannotated_count": len(_CANNED_FLAGGED),
        "annotated_count": 0,
        "annotations_uploaded": False,
        "stage_failed": None,
        "log_excerpt": None,
        "created_at": SERVER_TIMESTAMP,
        "updated_at": SERVER_TIMESTAMP,
    }
    doc_id = create_doc(COLLECTION, payload)
    logger.info("Created job %s", doc_id)
    return CreateJobResponse(job_id=doc_id, stage=JobStatus.pre_masking.value)


def get_job_progress(job_id: str) -> JobProgress | None:
    """Return the FE-facing JobProgress for *job_id*, or None if not found."""
    data = get_doc(COLLECTION, job_id)
    if data is None:
        return None

    stage = data.get("status", "error")
    epoch = data.get("epoch")
    total_epochs = data.get("total_epochs", 10)
    progress = _compute_progress(stage, epoch, total_epochs)

    flagged: list[dict] | None = None  # type: ignore[type-arg]
    unannotated: int | None = None
    annotated: int | None = None

    if stage == "awaiting_annotation":
        flagged = data.get("flagged_images", _CANNED_FLAGGED)
        unannotated = data.get("unannotated_count")
        annotated = data.get("annotated_count")

    return JobProgress(
        stage=stage,
        progress=progress,
        flagged=flagged,
        unannotated_count=unannotated,
        annotated_count=annotated,
        epoch=epoch if stage == "training" else None,
        total_epochs=total_epochs if stage == "training" else None,
        stage_failed=data.get("stage_failed"),
        log_excerpt=data.get("log_excerpt"),
    )


def list_jobs() -> list[JobSummary]:
    """Return all jobs as FE-facing JobSummary list."""
    docs = query_docs(COLLECTION, limit=200)
    summaries: list[JobSummary] = []
    for doc in docs:
        try:
            summaries.append(
                JobSummary(
                    job_id=doc["id"],
                    prompt=doc.get("prompt", ""),
                    stage=doc.get("status", "error"),
                    risk_tier=doc.get("risk_tier"),
                    created_at=str(doc.get("created_at", "")),
                )
            )
        except Exception:
            logger.warning("Skipping malformed job %s in list", doc.get("id"))
    return summaries
