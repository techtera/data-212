"""V3-M3: Integration tests verifying broker dispatch from job routes.

Covers:
    - POST /jobs enqueues a pre_masking BrokerTask with correct job_id + step
    - POST /jobs hop token in the enqueued task is a valid pre_masking JWT
    - POST /jobs/{id}/approve enqueues a training BrokerTask
    - POST /jobs/{id}/approve hop token is a valid training JWT
    - POST /jobs/{id}/rerun enqueues a pre_masking BrokerTask for the new job_id
    - BackgroundTasks parameter is NOT present on any of the three routes
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import AsyncClient

from src.config import get_settings

# ── Shared fixtures ────────────────────────────────────────────────────────────

_JOB_ID = "job_v3_001"
_NEW_JOB_ID = "job_v3_002"

_BASE_DOC = {
    "prompt": "v3 test",
    "dataset_object_path": "datasets/v3/raw.zip",
    "status": "pre_masking",
    "owner_id": "dev-admin",
    "risk_tier": None,
    "epoch": None,
    "total_epochs": 10,
    "flagged_images": [],
    "unannotated_count": 0,
    "annotated_count": 0,
    "annotations_uploaded": False,
    "stage_failed": None,
    "log_excerpt": None,
    "created_at": "2026-08-12T00:00:00+00:00",
    "updated_at": "2026-08-12T00:00:00+00:00",
}


def _doc(**overrides):  # type: ignore[no-untyped-def]
    return {**_BASE_DOC, **overrides}


# ── POST /jobs — broker dispatch ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_job_enqueues_pre_masking_broker_task(
    client: AsyncClient, auth_headers: dict
) -> None:
    """POST /jobs must enqueue a BrokerTask with task_type='pre_masking'."""
    mock_enqueue = AsyncMock()

    with (
        patch("src.services.job_service.create_doc", return_value=_JOB_ID),
        patch("src.services.job_service.get_doc", return_value=_doc()),
        patch(
            "src.routes.job_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
        patch("src.middleware.quota.query_docs", return_value=[]),
    ):
        resp = await client.post(
            "/jobs",
            json={"prompt": "v3 test", "dataset_object_path": "datasets/v3/raw.zip"},
            headers=auth_headers,
        )

    assert resp.status_code == 201
    mock_enqueue.assert_awaited_once()
    task = mock_enqueue.call_args[0][0]
    assert task.job_id == _JOB_ID
    assert task.task_type == "pre_masking"


@pytest.mark.asyncio
async def test_create_job_hop_token_is_valid_pre_masking_jwt(
    client: AsyncClient, auth_headers: dict
) -> None:
    """The hop token placed on the BrokerTask must be a valid pre_masking JWT."""
    mock_enqueue = AsyncMock()
    settings = get_settings()

    with (
        patch("src.services.job_service.create_doc", return_value=_JOB_ID),
        patch("src.services.job_service.get_doc", return_value=_doc()),
        patch(
            "src.routes.job_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
        patch("src.middleware.quota.query_docs", return_value=[]),
    ):
        await client.post(
            "/jobs",
            json={"prompt": "v3 test", "dataset_object_path": "datasets/v3/raw.zip"},
            headers=auth_headers,
        )

    task = mock_enqueue.call_args[0][0]
    # Decode and verify the hop token — must not raise
    payload = jwt.decode(
        task.hop_token,
        settings.jwt_hop_secret,
        algorithms=["HS256"],
        audience=settings.jwt_hop_audience,
    )
    assert payload["sub"] == _JOB_ID
    assert payload["step"] == "pre_masking"
    assert payload["iss"] == settings.jwt_hop_issuer


# ── POST /jobs/{id}/approve — broker dispatch ─────────────────────────────────


@pytest.mark.asyncio
async def test_approve_enqueues_training_broker_task(
    client: AsyncClient, auth_headers: dict
) -> None:
    """POST /jobs/{id}/approve must enqueue a BrokerTask with task_type='training'."""
    mock_enqueue = AsyncMock()

    with (
        patch(
            "src.services.job_service.get_doc",
            return_value=_doc(status="awaiting_approval"),
        ),
        patch("src.services.job_service.update_doc"),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
    ):
        resp = await client.post(f"/jobs/{_JOB_ID}/approve", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["stage"] == "training"
    mock_enqueue.assert_awaited_once()
    task = mock_enqueue.call_args[0][0]
    assert task.job_id == _JOB_ID
    assert task.task_type == "training"


@pytest.mark.asyncio
async def test_approve_hop_token_is_valid_training_jwt(
    client: AsyncClient, auth_headers: dict
) -> None:
    """The hop token on the training BrokerTask must be a valid training-scoped JWT."""
    mock_enqueue = AsyncMock()
    settings = get_settings()

    with (
        patch(
            "src.services.job_service.get_doc",
            return_value=_doc(status="awaiting_approval"),
        ),
        patch("src.services.job_service.update_doc"),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
    ):
        await client.post(f"/jobs/{_JOB_ID}/approve", headers=auth_headers)

    task = mock_enqueue.call_args[0][0]
    payload = jwt.decode(
        task.hop_token,
        settings.jwt_hop_secret,
        algorithms=["HS256"],
        audience=settings.jwt_hop_audience,
    )
    assert payload["sub"] == _JOB_ID
    assert payload["step"] == "training"


# ── POST /jobs/{id}/rerun — broker dispatch ───────────────────────────────────


@pytest.mark.asyncio
async def test_rerun_enqueues_pre_masking_for_new_job_id(
    client: AsyncClient, auth_headers: dict
) -> None:
    """POST /jobs/{id}/rerun must enqueue a pre_masking task for the NEW job_id."""
    mock_enqueue = AsyncMock()

    with (
        patch(
            "src.services.job_service.get_doc",
            side_effect=[_doc(status="done"), None],
        ),
        patch("src.services.job_service.create_doc", return_value=_NEW_JOB_ID),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
    ):
        resp = await client.post(f"/jobs/{_JOB_ID}/rerun", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["new_job_id"] == _NEW_JOB_ID
    mock_enqueue.assert_awaited_once()
    task = mock_enqueue.call_args[0][0]
    assert task.job_id == _NEW_JOB_ID  # must be the NEW job, not the original
    assert task.task_type == "pre_masking"


# ── No BackgroundTasks parameter ─────────────────────────────────────────────


def test_create_job_route_has_no_background_tasks_param() -> None:
    """V3: create_job handler must not declare a BackgroundTasks parameter."""
    from src.routes.job_routes import create_job

    sig = inspect.signature(create_job)
    param_annotations = [str(p.annotation) for p in sig.parameters.values()]
    assert "BackgroundTasks" not in " ".join(param_annotations)


def test_approve_job_route_has_no_background_tasks_param() -> None:
    """V3: approve_job handler must not declare a BackgroundTasks parameter."""
    from src.routes.job_action_routes import approve_job

    sig = inspect.signature(approve_job)
    param_annotations = [str(p.annotation) for p in sig.parameters.values()]
    assert "BackgroundTasks" not in " ".join(param_annotations)


def test_rerun_job_route_has_no_background_tasks_param() -> None:
    """V3: rerun_job handler must not declare a BackgroundTasks parameter."""
    from src.routes.job_action_routes import rerun_job

    sig = inspect.signature(rerun_job)
    param_annotations = [str(p.annotation) for p in sig.parameters.values()]
    assert "BackgroundTasks" not in " ".join(param_annotations)
