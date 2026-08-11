from __future__ import annotations

from unittest.mock import patch

from httpx import AsyncClient

from src.schemas.fe_contract import CreateJobResponse, JobProgress, JobSummary

# ── POST /jobs ────────────────────────────────────────────────────────────────


async def test_create_job_returns_201(client: AsyncClient, auth_headers: dict) -> None:
    """POST /jobs with valid payload must return 201 + job_id + stage."""
    mock_response = CreateJobResponse(job_id="job_001", stage="pre_masking")

    with patch("src.routes.job_routes.job_service.create_job", return_value=mock_response):
        resp = await client.post(
            "/jobs",
            json={"prompt": "train on my dataset", "dataset_object_path": "datasets/x/raw.zip"},
            headers=auth_headers,
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"] == "job_001"
    assert body["stage"] == "pre_masking"


async def test_create_job_missing_prompt_returns_422(
    client: AsyncClient, auth_headers: dict
) -> None:
    """POST /jobs without prompt must be rejected by Pydantic validation (422)."""
    resp = await client.post(
        "/jobs",
        json={"dataset_object_path": "datasets/x/raw.zip"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_create_job_missing_path_returns_422(client: AsyncClient, auth_headers: dict) -> None:
    """POST /jobs without dataset_object_path must return 422."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "train"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_create_job_no_auth_returns_401(client: AsyncClient) -> None:
    """POST /jobs without a token must return 401."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "train", "dataset_object_path": "datasets/x/raw.zip"},
    )
    assert resp.status_code == 401


async def test_create_job_wrong_auth_returns_401(
    client: AsyncClient, bad_auth_headers: dict
) -> None:
    """POST /jobs with a wrong token must return 401."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "train", "dataset_object_path": "datasets/x/raw.zip"},
        headers=bad_auth_headers,
    )
    assert resp.status_code == 401


# ── GET /jobs ─────────────────────────────────────────────────────────────────


async def test_list_jobs_returns_200_empty(client: AsyncClient, auth_headers: dict) -> None:
    """GET /jobs with no jobs returns 200 + empty list."""
    with patch("src.routes.job_routes.job_service.list_jobs", return_value=[]):
        resp = await client.get("/jobs", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_jobs_returns_summaries(client: AsyncClient, auth_headers: dict) -> None:
    """GET /jobs returns the list of JobSummary objects."""
    summaries = [
        JobSummary(
            job_id="job_001",
            prompt="train",
            stage="pre_masking",
            risk_tier=None,
            created_at="2026-08-11T10:00:00+00:00",
        ),
        JobSummary(
            job_id="job_002",
            prompt="retrain",
            stage="done",
            risk_tier="low",
            created_at="2026-08-11T11:00:00+00:00",
        ),
    ]
    with patch("src.routes.job_routes.job_service.list_jobs", return_value=summaries):
        resp = await client.get("/jobs", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["job_id"] == "job_001"
    assert body[0]["stage"] == "pre_masking"
    assert body[1]["risk_tier"] == "low"


async def test_list_jobs_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/jobs")
    assert resp.status_code == 401


# ── GET /jobs/{id} ────────────────────────────────────────────────────────────


async def test_get_job_returns_progress(client: AsyncClient, auth_headers: dict) -> None:
    """GET /jobs/{id} for an existing job returns 200 + progress."""
    progress = JobProgress(stage="pre_masking", progress=25)

    with patch("src.routes.job_routes.job_service.get_job_progress", return_value=progress):
        resp = await client.get("/jobs/job_001", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "pre_masking"
    assert body["progress"] == 25


async def test_get_job_with_flagged_images(client: AsyncClient, auth_headers: dict) -> None:
    """GET /jobs/{id} in awaiting_annotation stage returns flagged images."""
    progress = JobProgress(
        stage="awaiting_annotation",
        progress=50,
        flagged=[{"image_id": "9", "url": "/mock-data/flagged/9.png"}],
        unannotated_count=4,
        annotated_count=0,
    )
    with patch("src.routes.job_routes.job_service.get_job_progress", return_value=progress):
        resp = await client.get("/jobs/job_001", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "awaiting_annotation"
    assert body["progress"] == 50
    assert body["unannotated_count"] == 4
    assert len(body["flagged"]) == 1


async def test_get_job_training_returns_epoch(client: AsyncClient, auth_headers: dict) -> None:
    """GET /jobs/{id} in training stage exposes epoch/total_epochs."""
    progress = JobProgress(
        stage="training",
        progress=40,
        epoch=4,
        total_epochs=10,
    )
    with patch("src.routes.job_routes.job_service.get_job_progress", return_value=progress):
        resp = await client.get("/jobs/job_001", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["epoch"] == 4
    assert body["total_epochs"] == 10


async def test_get_job_not_found_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    """GET /jobs/{id} for an unknown id returns 404."""
    with patch("src.routes.job_routes.job_service.get_job_progress", return_value=None):
        resp = await client.get("/jobs/nonexistent", headers=auth_headers)

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


async def test_get_job_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/jobs/job_001")
    assert resp.status_code == 401


# ── job_service unit tests (no HTTP) ─────────────────────────────────────────


def test_compute_progress_all_stages() -> None:
    """_compute_progress must return the correct integer for every stage."""
    from src.services.job_service import _compute_progress

    assert _compute_progress("pre_masking", None, None) == 25
    assert _compute_progress("awaiting_annotation", None, None) == 50
    assert _compute_progress("awaiting_approval", None, None) == 75
    assert _compute_progress("training", 5, 10) == 50
    assert _compute_progress("training", 10, 10) == 100
    assert _compute_progress("done", None, None) == 100
    assert _compute_progress("rejected", None, None) == 0
    assert _compute_progress("error", None, None) == 0


def test_service_create_job_calls_create_doc() -> None:
    """job_service.create_job must call create_doc with correct status."""
    from src.schemas.fe_contract import CreateJobRequest
    from src.services.job_service import create_job

    req = CreateJobRequest(prompt="test", dataset_object_path="datasets/d/raw.zip")

    with (
        patch("src.services.job_service.create_doc", return_value="doc-new") as mock_create,
        patch("src.services.job_service.get_doc", return_value=None),
    ):
        result = create_job(req)

    assert result.job_id == "doc-new"
    assert result.stage == "pre_masking"
    payload = mock_create.call_args[0][1]
    assert payload["status"] == "pre_masking"
    assert payload["prompt"] == "test"


def test_service_get_job_progress_none_for_missing() -> None:
    from src.services.job_service import get_job_progress

    with patch("src.services.job_service.get_doc", return_value=None):
        result = get_job_progress("no-such-id")

    assert result is None


def test_service_list_jobs_returns_summaries() -> None:
    from src.services.job_service import list_jobs

    docs = [
        {
            "id": "j1",
            "prompt": "train",
            "status": "pre_masking",
            "risk_tier": None,
            "created_at": "2026-08-11T10:00:00+00:00",
        }
    ]
    with patch("src.services.job_service.query_docs", return_value=docs):
        results = list_jobs()

    assert len(results) == 1
    assert results[0].job_id == "j1"
    assert results[0].stage == "pre_masking"
