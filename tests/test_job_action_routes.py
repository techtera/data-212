from __future__ import annotations

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from src.schemas.fe_contract import (
    AnnotationsResponse,
    ApproveResponse,
    RejectResponse,
    RerunResponse,
)

# ── POST /jobs/{id}/annotations ───────────────────────────────────────────────


async def test_annotations_returns_200_awaiting_approval(
    client: AsyncClient, auth_headers: dict
) -> None:
    """POST annotations on a job in awaiting_annotation must return 200 + researching."""
    mock_resp = AnnotationsResponse(ok=True, stage="researching")

    with patch(
        "src.routes.job_action_routes.job_service.submit_annotations",
        return_value=mock_resp,
    ):
        resp = await client.post(
            "/jobs/job_001/annotations",
            json={"ack": True},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stage"] == "researching"


async def test_annotations_wrong_stage_returns_409(client: AsyncClient, auth_headers: dict) -> None:
    """POST annotations when not in awaiting_annotation must return 409."""
    with patch(
        "src.routes.job_action_routes.job_service.submit_annotations",
        side_effect=ValueError(
            "job job_001 is in stage 'pre_masking', expected 'awaiting_annotation'"
        ),
    ):
        resp = await client.post(
            "/jobs/job_001/annotations",
            json={"ack": True},
            headers=auth_headers,
        )

    assert resp.status_code == 409
    assert "pre_masking" in resp.json()["detail"]


async def test_annotations_unknown_job_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.job_action_routes.job_service.submit_annotations",
        side_effect=KeyError("job ghost not found"),
    ):
        resp = await client.post(
            "/jobs/ghost/annotations",
            json={"ack": True},
            headers=auth_headers,
        )

    assert resp.status_code == 404


async def test_annotations_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.post("/jobs/job_001/annotations", json={"ack": True})
    assert resp.status_code == 401


# ── POST /jobs/{id}/approve ───────────────────────────────────────────────────


async def test_approve_returns_200_training(client: AsyncClient, auth_headers: dict) -> None:
    """POST approve on awaiting_approval must return 200 + stage=training."""
    mock_resp = ApproveResponse(stage="training")

    with (
        patch(
            "src.routes.job_action_routes.job_service.approve_job",
            return_value=mock_resp,
        ),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=AsyncMock()),
        ),
    ):
        resp = await client.post("/jobs/job_001/approve", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["stage"] == "training"


async def test_approve_enqueues_training_broker_task(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Approve must enqueue a training BrokerTask via the broker."""
    mock_resp = ApproveResponse(stage="training")
    mock_enqueue = AsyncMock()

    with (
        patch(
            "src.routes.job_action_routes.job_service.approve_job",
            return_value=mock_resp,
        ),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
    ):
        await client.post("/jobs/job_001/approve", headers=auth_headers)

    mock_enqueue.assert_awaited_once()
    task = mock_enqueue.call_args[0][0]
    assert task.job_id == "job_001"
    assert task.task_type == "training"


async def test_approve_wrong_stage_returns_409(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.job_action_routes.job_service.approve_job",
        side_effect=ValueError("job job_001 is in stage 'training', expected 'awaiting_approval'"),
    ):
        resp = await client.post("/jobs/job_001/approve", headers=auth_headers)

    assert resp.status_code == 409


async def test_approve_unknown_job_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.job_action_routes.job_service.approve_job",
        side_effect=KeyError("not found"),
    ):
        resp = await client.post("/jobs/ghost/approve", headers=auth_headers)

    assert resp.status_code == 404


async def test_approve_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.post("/jobs/job_001/approve")
    assert resp.status_code == 401


# ── POST /jobs/{id}/reject ────────────────────────────────────────────────────


async def test_reject_returns_200_rejected(client: AsyncClient, auth_headers: dict) -> None:
    """POST reject on awaiting_approval must return 200 + stage=rejected."""
    mock_resp = RejectResponse(stage="rejected")

    with patch(
        "src.routes.job_action_routes.job_service.reject_job",
        return_value=mock_resp,
    ):
        resp = await client.post("/jobs/job_001/reject", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["stage"] == "rejected"


async def test_reject_wrong_stage_returns_409(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.job_action_routes.job_service.reject_job",
        side_effect=ValueError("wrong stage"),
    ):
        resp = await client.post("/jobs/job_001/reject", headers=auth_headers)

    assert resp.status_code == 409


async def test_reject_unknown_job_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.job_action_routes.job_service.reject_job",
        side_effect=KeyError("not found"),
    ):
        resp = await client.post("/jobs/ghost/reject", headers=auth_headers)

    assert resp.status_code == 404


async def test_reject_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.post("/jobs/job_001/reject")
    assert resp.status_code == 401


# ── POST /jobs/{id}/rerun ─────────────────────────────────────────────────────


async def test_rerun_returns_200_new_job(client: AsyncClient, auth_headers: dict) -> None:
    """POST rerun on a terminal job must return 200 + new_job_id."""
    mock_resp = RerunResponse(new_job_id="job_002", stage="pre_masking")

    with (
        patch(
            "src.routes.job_action_routes.job_service.rerun_job",
            return_value=mock_resp,
        ),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=AsyncMock()),
        ),
    ):
        resp = await client.post("/jobs/job_001/rerun", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["new_job_id"] == "job_002"
    assert body["stage"] == "pre_masking"


async def test_rerun_enqueues_pre_masking_for_new_job(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Rerun must enqueue a pre_masking BrokerTask for the NEW job id."""
    mock_resp = RerunResponse(new_job_id="job_NEW", stage="pre_masking")
    mock_enqueue = AsyncMock()

    with (
        patch(
            "src.routes.job_action_routes.job_service.rerun_job",
            return_value=mock_resp,
        ),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
    ):
        await client.post("/jobs/job_001/rerun", headers=auth_headers)

    mock_enqueue.assert_awaited_once()
    task = mock_enqueue.call_args[0][0]
    assert task.job_id == "job_NEW"
    assert task.task_type == "pre_masking"


async def test_rerun_non_terminal_returns_409(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.job_action_routes.job_service.rerun_job",
        side_effect=ValueError("job is in stage 'training'; rerun only allowed from terminal"),
    ):
        resp = await client.post("/jobs/job_001/rerun", headers=auth_headers)

    assert resp.status_code == 409


async def test_rerun_unknown_job_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.job_action_routes.job_service.rerun_job",
        side_effect=KeyError("not found"),
    ):
        resp = await client.post("/jobs/ghost/rerun", headers=auth_headers)

    assert resp.status_code == 404


async def test_rerun_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.post("/jobs/job_001/rerun")
    assert resp.status_code == 401


# ── Service-layer unit tests (no HTTP) ───────────────────────────────────────


def test_service_submit_annotations_updates_firestore() -> None:
    """submit_annotations must update Firestore with awaiting_approval status."""
    _doc = {
        "status": "awaiting_annotation",
        "prompt": "p",
        "dataset_object_path": "d",
    }
    with (
        patch("src.services.job_service.get_doc", return_value=_doc),
        patch("src.services.job_service.update_doc") as mock_update,
    ):
        from src.services.job_service import submit_annotations

        result = submit_annotations("job_001")

    assert result.ok is True
    assert result.stage == "researching"
    payload = mock_update.call_args[0][2]
    assert payload["status"] == "researching"
    assert payload["annotations_uploaded"] is True


def test_service_submit_annotations_wrong_stage_raises() -> None:
    _doc = {"status": "pre_masking"}
    with patch("src.services.job_service.get_doc", return_value=_doc):
        import pytest

        from src.services.job_service import submit_annotations

        with pytest.raises(ValueError, match="awaiting_annotation"):
            submit_annotations("job_001")


def test_service_approve_job_sets_training() -> None:
    _doc = {"status": "awaiting_approval"}
    with (
        patch("src.services.job_service.get_doc", return_value=_doc),
        patch("src.services.job_service.update_doc") as mock_update,
    ):
        from src.services.job_service import approve_job

        result = approve_job("job_001")

    assert result.stage == "training"
    payload = mock_update.call_args[0][2]
    assert payload["status"] == "training"
    assert payload["epoch"] == 1


def test_service_reject_job_sets_rejected() -> None:
    _doc = {"status": "awaiting_approval"}
    with (
        patch("src.services.job_service.get_doc", return_value=_doc),
        patch("src.services.job_service.update_doc") as mock_update,
    ):
        from src.services.job_service import reject_job

        result = reject_job("job_001")

    assert result.stage == "rejected"
    payload = mock_update.call_args[0][2]
    assert payload["status"] == "rejected"


def test_service_rerun_job_creates_new_job() -> None:
    _doc = {
        "status": "done",
        "prompt": "retrain",
        "dataset_object_path": "datasets/orig/raw.zip",
    }
    with (
        patch("src.services.job_service.get_doc", return_value=_doc),
        patch("src.services.job_service.create_doc", return_value="job_new") as mock_create,
    ):
        from src.services.job_service import rerun_job

        result = rerun_job("job_001")

    assert result.new_job_id == "job_new"
    assert result.stage == "pre_masking"
    payload = mock_create.call_args[0][1]
    assert payload["prompt"] == "retrain"
    assert payload["dataset_object_path"] == "datasets/orig/raw.zip"


def test_service_rerun_job_non_terminal_raises() -> None:
    _doc = {"status": "training"}
    with patch("src.services.job_service.get_doc", return_value=_doc):
        import pytest

        from src.services.job_service import rerun_job

        with pytest.raises(ValueError, match="terminal"):
            rerun_job("job_001")


def test_service_require_stage_missing_job_raises_key_error() -> None:
    with patch("src.services.job_service.get_doc", return_value=None):
        import pytest

        from src.services.job_service import _require_stage

        with pytest.raises(KeyError):
            _require_stage("ghost", "pre_masking")
