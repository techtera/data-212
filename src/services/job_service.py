from __future__ import annotations

import logging

from src.db.crud import create_doc, get_doc, query_docs, update_doc
from src.db.firebase import db  # noqa: F401  (imported to ensure Firebase is initialised)
from src.schemas.fe_contract import (
    AnnotationsResponse,
    ApproveResponse,
    CreateJobRequest,
    CreateJobResponse,
    JobProgress,
    JobSummary,
    RejectResponse,
    RerunResponse,
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
        case "researching":
            return 60
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


def create_job(req: CreateJobRequest, owner_id: str = "") -> CreateJobResponse:
    """Write a new job document and return the FE-facing CreateJobResponse.

    Maps FE fields (prompt, dataset_object_path) → Firestore document.
    Status is always forced to pre_masking on creation.
    owner_id is the authenticated user's Firestore user_id; defaults to ""
    for dev-token / legacy callers but must be set in production (V2+).
    """

    from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore[import-untyped]

    payload = {
        "prompt": req.prompt,
        "dataset_object_path": req.dataset_object_path,
        "dataset_description": req.dataset_description,
        "status": JobStatus.pre_masking.value,
        "owner_id": owner_id,  # V2: scopes the job to the creating user
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
    logger.info("Created job %s (owner logged separately)", doc_id)
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

    # V4: Include research findings when available (populated after researching stage)
    research_findings: str | None = data.get("research_findings")
    risk_tier: str | None = data.get("risk_tier")
    risk_reasoning: str | None = data.get("risk_reasoning")

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
        research_findings=research_findings,
        risk_tier=risk_tier,
        risk_reasoning=risk_reasoning,
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


# ── M4 action helpers ─────────────────────────────────────────────────────────


def _require_stage(job_id: str, required: str) -> dict:  # type: ignore[type-arg]
    """Fetch the job doc and assert it is in *required* stage.

    Returns the doc dict on success.
    Raises ValueError (→ 409 in the route) when the stage does not match.
    Raises KeyError (→ 404 in the route) when the job does not exist.
    """
    data = get_doc(COLLECTION, job_id)
    if data is None:
        raise KeyError(f"job {job_id} not found")
    current = data.get("status", "error")
    if current != required:
        raise ValueError(f"job {job_id} is in stage '{current}', expected '{required}'")
    return data


def submit_annotations(job_id: str) -> AnnotationsResponse:
    """Record that annotations have been uploaded and advance to researching.

    Guard: job must be in awaiting_annotation.
    In V1 the FE sends { ack: true } — no real COCO zip is processed here.
    V4: After annotations are submitted, the broker dispatches the research agent
    hop. The research agent returns findings which advance the job to
    awaiting_approval. The route handler is responsible for enqueuing the
    research task on the broker.
    """
    _require_stage(job_id, JobStatus.awaiting_annotation.value)
    update_doc(
        COLLECTION,
        job_id,
        {
            "status": JobStatus.researching.value,
            "annotations_uploaded": True,
            "annotated_count": 4,  # canned — matches flagged image count
            "unannotated_count": 0,
        },
    )
    logger.info("Job %s: annotations submitted → researching", job_id)
    return AnnotationsResponse(ok=True, stage=JobStatus.researching.value)


def approve_job(job_id: str) -> ApproveResponse:
    """Approve a job that is waiting for human review → advance to training.

    Guard: job must be in awaiting_approval.
    The caller is responsible for spawning run_training as a BackgroundTask.
    """
    _require_stage(job_id, JobStatus.awaiting_approval.value)
    update_doc(
        COLLECTION,
        job_id,
        {
            "status": JobStatus.training.value,
            "epoch": 1,
        },
    )
    logger.info("Job %s: approved → training", job_id)
    return ApproveResponse(stage=JobStatus.training.value)


def reject_job(job_id: str) -> RejectResponse:
    """Reject a job that is waiting for human review → terminate it.

    Guard: job must be in awaiting_approval.
    """
    _require_stage(job_id, JobStatus.awaiting_approval.value)
    update_doc(COLLECTION, job_id, {"status": JobStatus.rejected.value})
    logger.info("Job %s: rejected", job_id)
    return RejectResponse(stage=JobStatus.rejected.value)


def rerun_job(job_id: str) -> RerunResponse:
    """Create a brand-new job copying the prompt and dataset path of *job_id*.

    Guard: original job must be in a terminal stage (done | rejected | error | failed).
    The caller is responsible for spawning run_pre_masking for the new job.
    """
    _TERMINAL = {
        JobStatus.done.value,
        JobStatus.rejected.value,
        JobStatus.error.value,
        JobStatus.failed.value,
    }
    data = get_doc(COLLECTION, job_id)
    if data is None:
        raise KeyError(f"job {job_id} not found")
    current = data.get("status", "error")
    if current not in _TERMINAL:
        raise ValueError(
            f"job {job_id} is in stage '{current}'; "
            f"rerun is only allowed from terminal stages: {sorted(_TERMINAL)}"
        )

    new_req = CreateJobRequest(
        prompt=data.get("prompt", ""),
        dataset_object_path=data.get("dataset_object_path", ""),
    )
    # Preserve the original owner when re-running so quota tracking stays correct.
    original_owner = data.get("owner_id", "")
    new_response = create_job(new_req, owner_id=original_owner)
    logger.info("Job %s: re-run → new job %s", job_id, new_response.job_id)
    return RerunResponse(new_job_id=new_response.job_id, stage=new_response.stage)
