from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.schemas.job import JobCreate, JobResponse, JobStatus

# ── JobStatus ─────────────────────────────────────────────────────────────────


def test_job_status_values() -> None:
    """All six declared enum members must be accessible and equal their string value."""
    assert JobStatus.pre_masking.value == "pre_masking"
    assert JobStatus.awaiting_annotation.value == "awaiting_annotation"
    assert JobStatus.annotating.value == "annotating"
    assert JobStatus.approved.value == "approved"
    assert JobStatus.rejected.value == "rejected"
    assert JobStatus.failed.value == "failed"


def test_job_status_is_str_subclass() -> None:
    assert isinstance(JobStatus.pre_masking, str)


# ── JobCreate ─────────────────────────────────────────────────────────────────


def test_job_create_minimal() -> None:
    job = JobCreate(name="run-1", config={"epochs": 5})
    assert job.name == "run-1"
    assert job.config == {"epochs": 5}
    assert job.source_url is None


def test_job_create_with_source_url() -> None:
    job = JobCreate(
        name="run-2",
        config={"batch_size": 32},
        source_url="https://example.com/data.zip",
    )
    assert job.source_url == "https://example.com/data.zip"


def test_job_create_missing_name_raises() -> None:
    with pytest.raises(ValidationError):
        JobCreate(config={})  # type: ignore[call-arg]


def test_job_create_missing_config_raises() -> None:
    with pytest.raises(ValidationError):
        JobCreate(name="x")  # type: ignore[call-arg]


# ── JobResponse ───────────────────────────────────────────────────────────────


def _make_response(**overrides) -> JobResponse:  # type: ignore[no-untyped-def]
    now = datetime.now(tz=UTC)
    defaults = {
        "id": "test-id-001",
        "status": JobStatus.pre_masking,
        "name": "my-job",
        "config": {"epochs": 10},
        "source_url": None,
        "created_at": now,
        "updated_at": now,
    }
    return JobResponse(**{**defaults, **overrides})


def test_job_response_construction() -> None:
    resp = _make_response()
    assert resp.id == "test-id-001"
    assert resp.status == JobStatus.pre_masking
    assert resp.name == "my-job"


def test_job_response_serialises_datetimes_to_iso() -> None:
    """model_dump(mode='json') must emit ISO 8601 strings, not datetime objects."""
    resp = _make_response()
    dumped = resp.model_dump(mode="json")
    assert isinstance(dumped["created_at"], str)
    assert isinstance(dumped["updated_at"], str)
    # Must be parseable ISO 8601
    datetime.fromisoformat(dumped["created_at"])
    datetime.fromisoformat(dumped["updated_at"])


def test_job_response_round_trip() -> None:
    """Serialise to JSON dict then reconstruct — all fields must survive."""
    original = _make_response(source_url="https://example.com/d.zip")
    dumped = original.model_dump(mode="json")
    restored = JobResponse(**dumped)
    assert restored.id == original.id
    assert restored.status == original.status
    assert restored.source_url == original.source_url


def test_job_response_invalid_status_raises() -> None:
    """An unrecognised status string must be rejected by Pydantic."""
    now = datetime.now(tz=UTC)
    with pytest.raises(ValidationError):
        JobResponse(
            id="x",
            status="not_a_real_status",  # type: ignore[arg-type]
            name="x",
            config={},
            created_at=now,
            updated_at=now,
        )
