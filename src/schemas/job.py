from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_serializer


class JobStatus(StrEnum):
    """All valid lifecycle states for a training job."""

    pre_masking = "pre_masking"
    awaiting_annotation = "awaiting_annotation"
    annotating = "annotating"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"


class JobCreate(BaseModel):
    """Payload accepted by POST /jobs."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "my-segmentation-run",
                    "config": {"epochs": 10, "batch_size": 16},
                    "source_url": "https://storage.googleapis.com/bucket/dataset.zip",
                }
            ]
        }
    )

    name: str
    config: dict  # type: ignore[type-arg]
    source_url: str | None = None


class JobResponse(BaseModel):
    """Shape returned by every job-reading endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "abc123",
                    "status": "pre_masking",
                    "name": "my-segmentation-run",
                    "config": {"epochs": 10, "batch_size": 16},
                    "source_url": None,
                    "created_at": "2026-08-11T08:00:00+00:00",
                    "updated_at": "2026-08-11T08:00:00+00:00",
                }
            ]
        },
    )

    id: str
    status: JobStatus
    name: str
    config: dict  # type: ignore[type-arg]
    source_url: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, value: datetime) -> str:
        """Emit datetimes as ISO 8601 strings in all serialisation modes."""
        return value.isoformat()
