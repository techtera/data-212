"""Tests for src/middleware/quota.py

Verifies the per-user daily job quota:
- Under the limit: request passes through.
- At or over the limit: 429 is raised.
- Missing user_id in request.state: 401 is raised.
- DB error: fail open (request is allowed, not blocked).
- Integration: POST /jobs returns 429 when quota exceeded.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from src.schemas.fe_contract import CreateJobResponse


def _make_request(user_id: str = "user_abc") -> MagicMock:
    """Build a minimal mock Request with request.state.user_id set."""
    req = MagicMock()
    req.state = MagicMock()
    req.state.user_id = user_id
    return req


# ── Under the limit ───────────────────────────────────────────────────────────


def test_under_quota_allows_request():
    from src.middleware.quota import check_job_quota

    req = _make_request("user_1")
    # Return 19 jobs (default max is 20) — should pass.
    with patch("src.middleware.quota.query_docs", return_value=[{}] * 19):
        check_job_quota(req)  # must not raise


def test_zero_jobs_today_allowed():
    from src.middleware.quota import check_job_quota

    req = _make_request("user_2")
    with patch("src.middleware.quota.query_docs", return_value=[]):
        check_job_quota(req)  # must not raise


# ── At / over the limit ───────────────────────────────────────────────────────


def test_at_quota_limit_raises_429():
    from src.middleware.quota import check_job_quota

    req = _make_request("user_3")
    with (
        patch("src.middleware.quota.query_docs", return_value=[{}] * 20),
        pytest.raises(HTTPException) as exc_info,
    ):
        check_job_quota(req)
    assert exc_info.value.status_code == 429


def test_over_quota_raises_429():
    from src.middleware.quota import check_job_quota

    req = _make_request("user_4")
    # Simulate 21 jobs returned (fetch limit is max+1).
    with (
        patch("src.middleware.quota.query_docs", return_value=[{}] * 21),
        pytest.raises(HTTPException) as exc_info,
    ):
        check_job_quota(req)
    assert exc_info.value.status_code == 429


def test_429_detail_mentions_limit():
    from src.middleware.quota import check_job_quota

    req = _make_request("user_5")
    with (
        patch("src.middleware.quota.query_docs", return_value=[{}] * 20),
        pytest.raises(HTTPException) as exc_info,
    ):
        check_job_quota(req)
    assert "20" in exc_info.value.detail


# ── Missing user_id ───────────────────────────────────────────────────────────


def test_missing_user_id_raises_401():
    from src.middleware.quota import check_job_quota

    req = MagicMock()
    req.state = MagicMock()
    req.state.user_id = ""  # empty — not set by require_auth

    with pytest.raises(HTTPException) as exc_info:
        check_job_quota(req)
    assert exc_info.value.status_code == 401


def test_no_user_id_attribute_raises_401():
    from src.middleware.quota import check_job_quota

    req = MagicMock()
    # state exists but user_id attribute is missing entirely.
    del req.state.user_id

    with pytest.raises(HTTPException) as exc_info:
        check_job_quota(req)
    assert exc_info.value.status_code == 401


# ── DB error — fail open ──────────────────────────────────────────────────────


def test_db_error_fails_open():
    """A Firestore exception must NOT block the user — fail open on quota."""
    from src.middleware.quota import check_job_quota

    req = _make_request("user_6")
    with patch("src.middleware.quota.query_docs", side_effect=Exception("DB down")):
        check_job_quota(req)  # must not raise — fail open


# ── Integration: POST /jobs returns 429 when quota reached ───────────────────


@pytest.mark.asyncio
async def test_create_job_returns_429_when_quota_reached(client: AsyncClient, auth_headers: dict):
    payload = {
        "prompt": "quota test job",
        "dataset_object_path": "datasets/ds_test/raw.zip",
    }
    # Patch query_docs to return max jobs (20) for this user.
    with patch("src.middleware.quota.query_docs", return_value=[{}] * 20):
        resp = await client.post("/jobs", json=payload, headers=auth_headers)
    assert resp.status_code == 429
    assert "limit" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_job_allowed_under_quota(client: AsyncClient, auth_headers: dict):
    payload = {
        "prompt": "allowed job",
        "dataset_object_path": "datasets/ds_test/raw.zip",
    }

    with (
        patch("src.middleware.quota.query_docs", return_value=[{}] * 5),
        patch("src.routes.job_routes.object_exists", return_value=True),
        patch("src.services.job_service.create_job") as mock_create,
    ):
        mock_create.return_value = CreateJobResponse(job_id="job_quota_test", stage="pre_masking")
        resp = await client.post("/jobs", json=payload, headers=auth_headers)

    # 201 or any non-429 means quota didn't block it.
    assert resp.status_code != 429
