from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from src.schemas.job import JobCreate, JobStatus

# ── Fixtures / helpers ────────────────────────────────────────────────────────

NOW_ISO = "2026-08-11T10:00:00+00:00"
NOW_DT = datetime(2026, 8, 11, 10, 0, 0, tzinfo=UTC)

_BASE_DOC = {
    "name": "my-job",
    "config": {"epochs": 5},
    "source_url": None,
    "status": "pre_masking",
    "created_at": NOW_ISO,
    "updated_at": NOW_ISO,
}


# ── create_job ────────────────────────────────────────────────────────────────


def test_create_job_returns_job_response() -> None:
    job_in = JobCreate(name="my-job", config={"epochs": 5})

    with (
        patch("src.db.jobs.create_doc", return_value="doc-abc") as mock_create,
        patch("src.db.jobs.get_doc", return_value=_BASE_DOC) as mock_get,
    ):
        from src.db.jobs import create_job

        result = create_job(job_in)

    assert result.id == "doc-abc"
    assert result.status == JobStatus.pre_masking
    assert result.name == "my-job"
    assert result.config == {"epochs": 5}
    assert result.source_url is None
    mock_create.assert_called_once()
    mock_get.assert_called_once_with("jobs", "doc-abc")


def test_create_job_status_is_always_pre_masking() -> None:
    """The caller cannot force a different initial status."""
    job_in = JobCreate(name="forced", config={})

    with (
        patch("src.db.jobs.create_doc", return_value="x") as mock_create,
        patch("src.db.jobs.get_doc", return_value={**_BASE_DOC, "name": "forced", "config": {}}),
    ):
        from src.db.jobs import create_job

        result = create_job(job_in)

    payload_sent = mock_create.call_args[0][1]
    assert payload_sent["status"] == JobStatus.pre_masking.value
    assert result.status == JobStatus.pre_masking


def test_create_job_passes_source_url() -> None:
    job_in = JobCreate(name="u", config={}, source_url="https://x.com/d.zip")
    doc = {**_BASE_DOC, "name": "u", "config": {}, "source_url": "https://x.com/d.zip"}

    with (
        patch("src.db.jobs.create_doc", return_value="doc-url"),
        patch("src.db.jobs.get_doc", return_value=doc),
    ):
        from src.db.jobs import create_job

        result = create_job(job_in)

    assert result.source_url == "https://x.com/d.zip"


# ── get_job ───────────────────────────────────────────────────────────────────


def test_get_job_returns_job_response() -> None:
    with patch("src.db.jobs.get_doc", return_value=_BASE_DOC):
        from src.db.jobs import get_job

        result = get_job("doc-abc")

    assert result is not None
    assert result.id == "doc-abc"
    assert result.status == JobStatus.pre_masking


def test_get_job_returns_none_for_missing() -> None:
    with patch("src.db.jobs.get_doc", return_value=None):
        from src.db.jobs import get_job

        result = get_job("does-not-exist")

    assert result is None


# ── update_job_status ─────────────────────────────────────────────────────────


def test_update_job_status_calls_update_doc() -> None:
    with patch("src.db.jobs.update_doc") as mock_update:
        from src.db.jobs import update_job_status

        update_job_status("doc-abc", JobStatus.approved)

    mock_update.assert_called_once_with("jobs", "doc-abc", {"status": "approved"})


def test_update_job_status_rejected() -> None:
    with patch("src.db.jobs.update_doc") as mock_update:
        from src.db.jobs import update_job_status

        update_job_status("doc-xyz", JobStatus.rejected)

    mock_update.assert_called_once_with("jobs", "doc-xyz", {"status": "rejected"})


# ── list_jobs ─────────────────────────────────────────────────────────────────


def test_list_jobs_returns_list() -> None:
    docs = [
        {"id": "j1", **_BASE_DOC},
        {"id": "j2", **{**_BASE_DOC, "name": "other-job"}},
    ]
    with patch("src.db.jobs.query_docs", return_value=docs):
        from src.db.jobs import list_jobs

        results = list_jobs()

    assert len(results) == 2
    assert results[0].id == "j1"
    assert results[1].name == "other-job"


def test_list_jobs_empty() -> None:
    with patch("src.db.jobs.query_docs", return_value=[]):
        from src.db.jobs import list_jobs

        results = list_jobs(limit=10)

    assert results == []


def test_list_jobs_skips_malformed_docs() -> None:
    """A document missing required fields must be silently skipped."""
    docs = [
        {"id": "good", **_BASE_DOC},
        {"id": "bad"},  # missing name, status, etc.
    ]
    with patch("src.db.jobs.query_docs", return_value=docs):
        from src.db.jobs import list_jobs

        results = list_jobs()

    assert len(results) == 1
    assert results[0].id == "good"
