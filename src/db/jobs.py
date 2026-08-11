from __future__ import annotations

import logging
from datetime import UTC, datetime

from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore[import-untyped]

from src.db.crud import create_doc, get_doc, query_docs, update_doc
from src.schemas.job import JobCreate, JobResponse, JobStatus

logger = logging.getLogger(__name__)

COLLECTION = "jobs"


def _parse_dt(value: str | datetime | None) -> datetime:
    """Coerce an ISO string or datetime to a UTC-aware datetime.

    Firestore SERVER_TIMESTAMP fields are resolved to real datetimes after the
    document is read back; ISO strings arrive from _convert_timestamps.
    Falls back to utcnow() if value is None (e.g. immediately after a write
    where the server timestamp has not yet propagated).
    """
    if value is None:
        return datetime.now(tz=UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    # ISO string → datetime
    return datetime.fromisoformat(value)


def _doc_to_response(doc_id: str, data: dict) -> JobResponse:  # type: ignore[type-arg]
    return JobResponse(
        id=doc_id,
        status=JobStatus(data["status"]),
        name=data["name"],
        config=data.get("config", {}),
        source_url=data.get("source_url"),
        created_at=_parse_dt(data.get("created_at")),
        updated_at=_parse_dt(data.get("updated_at")),
    )


# ── Public API ────────────────────────────────────────────────────────────────


def create_job(job_create: JobCreate) -> JobResponse:
    """Persist a new job document and return the full JobResponse.

    Status is always forced to `pre_masking` on creation regardless of the
    payload — the caller has no power to set an arbitrary initial status.
    """
    payload = {
        "name": job_create.name,
        "config": job_create.config,
        "source_url": job_create.source_url,
        "status": JobStatus.pre_masking.value,
        "created_at": SERVER_TIMESTAMP,
        "updated_at": SERVER_TIMESTAMP,
    }
    doc_id = create_doc(COLLECTION, payload)

    # Read the document back so timestamps are real values, not sentinels.
    data = get_doc(COLLECTION, doc_id) or {}
    return _doc_to_response(doc_id, {**payload, **data})


def get_job(job_id: str) -> JobResponse | None:
    """Return the JobResponse for *job_id*, or None if not found."""
    data = get_doc(COLLECTION, job_id)
    if data is None:
        return None
    return _doc_to_response(job_id, data)


def update_job_status(job_id: str, status: JobStatus) -> None:
    """Update only the status field of a job (updated_at is set server-side)."""
    update_doc(COLLECTION, job_id, {"status": status.value})
    logger.info("Job %s status → %s", job_id, status.value)


def list_jobs(limit: int = 100) -> list[JobResponse]:
    """Return up to *limit* jobs ordered by insertion order (Firestore default)."""
    docs = query_docs(COLLECTION, limit=limit)
    results: list[JobResponse] = []
    for doc in docs:
        doc_id = doc.pop("id")
        try:
            results.append(_doc_to_response(doc_id, doc))
        except Exception:
            logger.warning("Skipping malformed job document %s", doc_id)
    return results
