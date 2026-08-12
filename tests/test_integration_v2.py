"""Full V2 end-to-end integration test.

Flow exercised:
  register → login → create job (owner_id injected) → poll pre_masking
  → poll awaiting_annotation → submit annotations → poll awaiting_approval
  → approve → poll training → poll done → results → inference → logout

All Firestore and background-task calls are mocked so the test is
deterministic and requires no real Firebase connection.  The test client
hits the real FastAPI router layer so auth, quota, routing, and schema
validation are all exercised.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

# ── Shared mock data ──────────────────────────────────────────────────────────

_USER_ID = "user_e2e_001"
_JOB_ID = "job_e2e_001"

_FAKE_USER = {
    "id": _USER_ID,
    "email": "e2e@terafac.dev",
    "password_hash": "",
    "display_name": "E2E User",
    "is_active": True,
    "created_at": "2026-08-12T00:00:00+00:00",
}

_BASE_JOB_DOC = {
    "prompt": "e2e test job",
    "dataset_object_path": "datasets/ds_e2e/raw.zip",
    "status": "pre_masking",
    "owner_id": _USER_ID,
    "risk_tier": None,
    "epoch": None,
    "total_epochs": 10,
    "flagged_images": [
        {"image_id": "9", "url": "/mock-data/flagged/9.png"},
        {"image_id": "10", "url": "/mock-data/flagged/10.png"},
        {"image_id": "11", "url": "/mock-data/flagged/11.png"},
        {"image_id": "12", "url": "/mock-data/flagged/12.png"},
    ],
    "unannotated_count": 4,
    "annotated_count": 0,
    "annotations_uploaded": False,
    "stage_failed": None,
    "log_excerpt": None,
    "created_at": "2026-08-12T00:00:00+00:00",
    "updated_at": "2026-08-12T00:00:00+00:00",
}


def _job(**overrides):  # type: ignore[no-untyped-def]
    return {**_BASE_JOB_DOC, **overrides}


def _mock_session_db() -> MagicMock:
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.set.return_value = None
    return mock_db


# ── Helper: get a live session token via the real /auth/register endpoint ─────


async def _register_and_get_token(client: AsyncClient) -> str:
    """Register a test user and return the raw access token."""
    with (
        patch("src.routes.auth_routes.db_users.get_user_by_email", return_value=None),
        patch("src.routes.auth_routes.db_users.create_user", return_value=_USER_ID),
        patch("src.db.sessions.db", _mock_session_db()),
    ):
        resp = await client.post(
            "/auth/register",
            json={
                "email": "e2e@terafac.dev",
                "password": "e2epassword1",
                "display_name": "E2E User",
            },
        )
    assert resp.status_code == 201
    return resp.json()["access_token"]


# ── 1. Register ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_register_creates_user(client: AsyncClient):
    with (
        patch("src.routes.auth_routes.db_users.get_user_by_email", return_value=None),
        patch("src.routes.auth_routes.db_users.create_user", return_value=_USER_ID),
        patch("src.db.sessions.db", _mock_session_db()),
    ):
        resp = await client.post(
            "/auth/register",
            json={
                "email": "e2e@terafac.dev",
                "password": "e2epassword1",
                "display_name": "E2E User",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


# ── 2. Login ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_login_returns_token(client: AsyncClient):
    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=_FAKE_USER),
        patch("src.services.auth_service.verify_password", return_value=True),
        patch("src.db.sessions.db", _mock_session_db()),
    ):
        resp = await client.post(
            "/auth/login",
            json={"email": "e2e@terafac.dev", "password": "e2epassword1"},
        )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


# ── 3. Create job — owner_id injected ────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_create_job_stores_owner_id(client: AsyncClient, auth_headers: dict):
    """POST /jobs must store owner_id from request.state on the Firestore doc."""
    with (
        patch("src.services.job_service.create_doc", return_value=_JOB_ID) as mock_create,
        patch("src.services.job_service.get_doc", return_value=_job()),
        patch("src.routes.job_routes.stubs.run_pre_masking"),
        patch("src.middleware.quota.query_docs", return_value=[]),
    ):
        resp = await client.post(
            "/jobs",
            json={
                "prompt": "e2e test job",
                "dataset_object_path": "datasets/ds_e2e/raw.zip",
            },
            headers=auth_headers,
        )

    assert resp.status_code == 201
    assert resp.json()["job_id"] == _JOB_ID

    # Verify owner_id was passed to create_doc
    payload = mock_create.call_args[0][1]
    assert "owner_id" in payload
    # dev-admin is the user_id when ALLOW_DEV_TOKEN=true (set in conftest)
    assert payload["owner_id"] == "dev-admin"


@pytest.mark.asyncio
async def test_e2e_create_job_owner_id_not_empty_for_real_session(
    client: AsyncClient,
):
    """When a real session token is presented, owner_id must be the real user_id."""
    # Build a real-ish session: mock session lookup to return a valid session doc
    # and user doc so require_auth sets request.state.user_id = _USER_ID.
    from datetime import UTC, datetime, timedelta

    future = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    fake_session = {
        "user_id": _USER_ID,
        "expires_at": future,
        "revoked": False,
    }

    with (
        patch(
            "src.middleware.auth.db_sessions.get_session_by_token_hash", return_value=fake_session
        ),
        patch("src.middleware.auth.db_users.get_user_by_id", return_value=_FAKE_USER),
        patch("src.services.job_service.create_doc", return_value=_JOB_ID) as mock_create,
        patch("src.services.job_service.get_doc", return_value=_job()),
        patch("src.routes.job_routes.stubs.run_pre_masking"),
        patch("src.middleware.quota.query_docs", return_value=[]),
    ):
        resp = await client.post(
            "/jobs",
            json={
                "prompt": "real owner test",
                "dataset_object_path": "datasets/ds_e2e/raw.zip",
            },
            headers={"Authorization": "Bearer some-real-token"},
        )

    assert resp.status_code == 201
    payload = mock_create.call_args[0][1]
    assert payload["owner_id"] == _USER_ID


# ── 4. Poll — pre_masking ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_poll_pre_masking(client: AsyncClient, auth_headers: dict):
    with patch("src.services.job_service.get_doc", return_value=_job(status="pre_masking")):
        resp = await client.get(f"/jobs/{_JOB_ID}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "pre_masking"
    assert body["progress"] == 25


# ── 5. Poll — awaiting_annotation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_poll_awaiting_annotation(client: AsyncClient, auth_headers: dict):
    with patch(
        "src.services.job_service.get_doc",
        return_value=_job(status="awaiting_annotation"),
    ):
        resp = await client.get(f"/jobs/{_JOB_ID}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "awaiting_annotation"
    assert body["progress"] == 50
    assert body["unannotated_count"] == 4


# ── 6. Submit annotations ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_submit_annotations(client: AsyncClient, auth_headers: dict):
    with (
        patch(
            "src.services.job_service.get_doc",
            return_value=_job(status="awaiting_annotation"),
        ),
        patch("src.services.job_service.update_doc"),
    ):
        resp = await client.post(
            f"/jobs/{_JOB_ID}/annotations",
            json={"ack": True},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stage"] == "awaiting_approval"


# ── 7. Poll — awaiting_approval ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_poll_awaiting_approval(client: AsyncClient, auth_headers: dict):
    with patch(
        "src.services.job_service.get_doc",
        return_value=_job(status="awaiting_approval", risk_tier="medium"),
    ):
        resp = await client.get(f"/jobs/{_JOB_ID}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "awaiting_approval"
    assert body["progress"] == 75


# ── 8. Approve ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_approve_job(client: AsyncClient, auth_headers: dict):
    with (
        patch(
            "src.services.job_service.get_doc",
            return_value=_job(status="awaiting_approval"),
        ),
        patch("src.services.job_service.update_doc"),
        patch("src.routes.job_action_routes.stubs.run_training"),
    ):
        resp = await client.post(f"/jobs/{_JOB_ID}/approve", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["stage"] == "training"


# ── 9. Poll — training ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_poll_training(client: AsyncClient, auth_headers: dict):
    with patch(
        "src.services.job_service.get_doc",
        return_value=_job(status="training", epoch=5, total_epochs=10),
    ):
        resp = await client.get(f"/jobs/{_JOB_ID}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "training"
    assert body["epoch"] == 5
    assert body["total_epochs"] == 10


# ── 10. Poll — done ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_poll_done(client: AsyncClient, auth_headers: dict):
    with patch("src.services.job_service.get_doc", return_value=_job(status="done")):
        resp = await client.get(f"/jobs/{_JOB_ID}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "done"
    assert body["progress"] == 100


# ── 11. Results ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_results(client: AsyncClient, auth_headers: dict):
    with patch("src.services.data_service.get_doc", return_value=_job(status="done")):
        resp = await client.get(f"/jobs/{_JOB_ID}/results", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "final_metrics" in body
    assert "sample_predictions" in body
    assert "risk_tier" in body


# ── 12. Inference ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_inference(client: AsyncClient, auth_headers: dict):
    with patch("src.services.data_service.get_doc", return_value=_job(status="done")):
        resp = await client.get(f"/jobs/{_JOB_ID}/inference", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "code" in body
    assert "checkpoint_signed_url" in body


# ── 13. Logout ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_logout(client: AsyncClient, auth_headers: dict):
    with patch("src.routes.auth_routes.invalidate_session"):
        resp = await client.post("/auth/logout", headers=auth_headers)
    assert resp.status_code == 204


# ── 14. After logout — job create must still require auth ─────────────────────


@pytest.mark.asyncio
async def test_e2e_no_token_rejected(client: AsyncClient):
    resp = await client.post(
        "/jobs",
        json={"prompt": "sneaky", "dataset_object_path": "datasets/x/raw.zip"},
    )
    assert resp.status_code == 401


# ── 15. owner_id on rerun inherits from original job ─────────────────────────


@pytest.mark.asyncio
async def test_e2e_rerun_inherits_owner_id(client: AsyncClient, auth_headers: dict):
    """Re-running a done job must copy owner_id to the new job document."""
    with (
        patch(
            "src.services.job_service.get_doc",
            side_effect=[
                _job(status="done"),  # rerun reads original job
                None,  # create_job's internal get_doc
            ],
        ),
        patch("src.services.job_service.create_doc", return_value="job_rerun_001") as mock_create,
        patch("src.routes.job_action_routes.stubs.run_pre_masking"),
    ):
        resp = await client.post(f"/jobs/{_JOB_ID}/rerun", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["new_job_id"] == "job_rerun_001"

    payload = mock_create.call_args[0][1]
    assert payload["owner_id"] == _USER_ID
