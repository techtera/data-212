"""Tests for V4-GCS-M2 — training data fetch via signed URLs.

Verifies:
- approve_job mints signed GET URLs for dataset + weights
- approve_job mints signed PUT URLs for results upload
- BrokerTask.payload carries the signed URLs
- stubs.run_training accepts gcs_urls parameter
- Signed URL values are never logged
- GCS minting failure does not block training dispatch (non-fatal for stubs)
- get_job_dataset_path returns the correct path
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

HEADERS = {"Authorization": "Bearer dev-token-change-me", "Content-Type": "application/json"}


# ── get_job_dataset_path ──────────────────────────────────────────────────────


def test_get_job_dataset_path_returns_path() -> None:
    """get_job_dataset_path should return the dataset_object_path from the doc."""
    from src.services.job_service import get_job_dataset_path

    with patch(
        "src.services.job_service.get_doc",
        return_value={"dataset_object_path": "datasets/ds_abc/raw.zip"},
    ):
        result = get_job_dataset_path("job_001")
    assert result == "datasets/ds_abc/raw.zip"


def test_get_job_dataset_path_returns_none_for_missing_job() -> None:
    """get_job_dataset_path should return None when job not found."""
    from src.services.job_service import get_job_dataset_path

    with patch("src.services.job_service.get_doc", return_value=None):
        result = get_job_dataset_path("ghost")
    assert result is None


# ── approve_job mints GCS signed URLs ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_mints_gcs_urls_in_broker_payload(client: AsyncClient) -> None:
    """POST /jobs/{id}/approve must include GCS signed URLs in BrokerTask.payload."""
    mock_enqueue = AsyncMock()

    with (
        patch(
            "src.services.job_service.get_doc",
            return_value={
                "status": "awaiting_approval",
                "dataset_object_path": "datasets/ds_x/raw.zip",
            },
        ),
        patch("src.services.job_service.update_doc"),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
        patch(
            "src.routes.job_action_routes.mint_signed_get_url",
            side_effect=["https://get-dataset-url", "https://get-weights-url"],
        ) as mock_get,
        patch(
            "src.routes.job_action_routes.mint_signed_put_url",
            side_effect=["https://put-results-url", "https://put-metrics-url"],
        ) as mock_put,
        patch(
            "src.routes.job_action_routes.job_service.get_job_dataset_path",
            return_value="datasets/ds_x/raw.zip",
        ),
    ):
        resp = await client.post("/jobs/job_001/approve", headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["stage"] == "training"

    # Verify BrokerTask payload contains the signed URLs
    mock_enqueue.assert_awaited_once()
    task = mock_enqueue.call_args[0][0]
    assert task.payload["dataset_signed_url"] == "https://get-dataset-url"
    assert task.payload["weights_signed_url"] == "https://get-weights-url"
    assert task.payload["results_upload_url"] == "https://put-results-url"
    assert task.payload["results_metrics_url"] == "https://put-metrics-url"

    # Verify correct GCS paths were requested
    mock_get.assert_any_call("datasets/ds_x/raw.zip")
    mock_get.assert_any_call("weights/base.pt")
    mock_put.assert_any_call("results/job_001/best.pt", content_type="application/octet-stream")
    mock_put.assert_any_call("results/job_001/metrics.json", content_type="application/json")


@pytest.mark.asyncio
async def test_approve_continues_on_gcs_failure(client: AsyncClient) -> None:
    """Training must still dispatch even when GCS URL minting fails (non-fatal for stubs)."""
    from src.services.gcs_service import GCSServiceError

    mock_enqueue = AsyncMock()

    with (
        patch(
            "src.services.job_service.get_doc",
            return_value={
                "status": "awaiting_approval",
                "dataset_object_path": "datasets/x/raw.zip",
            },
        ),
        patch("src.services.job_service.update_doc"),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
        patch(
            "src.routes.job_action_routes.mint_signed_get_url",
            side_effect=GCSServiceError("SA key missing"),
        ),
        patch(
            "src.routes.job_action_routes.job_service.get_job_dataset_path",
            return_value="datasets/x/raw.zip",
        ),
    ):
        resp = await client.post("/jobs/job_001/approve", headers=HEADERS)

    # Should still succeed — GCS failure is non-fatal for stub training
    assert resp.status_code == 200
    mock_enqueue.assert_awaited_once()
    task = mock_enqueue.call_args[0][0]
    # Payload should be empty since minting failed
    assert task.payload == {}


@pytest.mark.asyncio
async def test_approve_empty_payload_when_no_dataset_path(client: AsyncClient) -> None:
    """If dataset_object_path is missing from job doc, payload should be empty."""
    mock_enqueue = AsyncMock()

    with (
        patch(
            "src.services.job_service.get_doc",
            return_value={"status": "awaiting_approval"},
        ),
        patch("src.services.job_service.update_doc"),
        patch(
            "src.routes.job_action_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
        patch(
            "src.routes.job_action_routes.job_service.get_job_dataset_path",
            return_value=None,
        ),
    ):
        resp = await client.post("/jobs/job_001/approve", headers=HEADERS)

    assert resp.status_code == 200
    task = mock_enqueue.call_args[0][0]
    assert task.payload == {}


# ── stubs.run_training accepts gcs_urls ───────────────────────────────────────


@pytest.mark.asyncio
async def test_run_training_accepts_gcs_urls_parameter() -> None:
    """run_training must accept the gcs_urls keyword argument without error."""
    from src.services.stubs import run_training

    fake_urls = {
        "dataset_signed_url": "https://fake-dataset-url",
        "weights_signed_url": "https://fake-weights-url",
        "results_upload_url": "https://fake-results-url",
    }

    with (
        patch("src.db.crud.get_doc", return_value={"status": "training"}),
        patch("src.services.stubs.update_doc"),
        patch("src.services.stubs.asyncio.sleep", return_value=None),
    ):
        # Should not raise
        await run_training("job_test", gcs_urls=fake_urls)


@pytest.mark.asyncio
async def test_run_training_works_without_gcs_urls() -> None:
    """run_training must still work with gcs_urls=None (backward compat)."""
    from src.services.stubs import run_training

    with (
        patch("src.db.crud.get_doc", return_value={"status": "training"}),
        patch("src.services.stubs.update_doc"),
        patch("src.services.stubs.asyncio.sleep", return_value=None),
    ):
        await run_training("job_test")  # no gcs_urls argument


# ── Security: signed URLs never logged ────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_training_does_not_log_url_values(caplog) -> None:
    """Signed URL values must NEVER appear in logs — only key names are logged."""
    import logging

    from src.services.stubs import run_training

    fake_urls = {
        "dataset_signed_url": "https://SECRET-DATASET-TOKEN",
        "weights_signed_url": "https://SECRET-WEIGHTS-TOKEN",
        "results_upload_url": "https://SECRET-RESULTS-TOKEN",
    }

    with (
        caplog.at_level(logging.DEBUG, logger="src.services.stubs"),
        patch("src.db.crud.get_doc", return_value={"status": "training"}),
        patch("src.services.stubs.update_doc"),
        patch("src.services.stubs.asyncio.sleep", return_value=None),
    ):
        await run_training("job_test", gcs_urls=fake_urls)

    # URL values must not appear in logs
    assert "SECRET-DATASET-TOKEN" not in caplog.text
    assert "SECRET-WEIGHTS-TOKEN" not in caplog.text
    assert "SECRET-RESULTS-TOKEN" not in caplog.text
    # But the key names should be present (metadata)
    assert "dataset_signed_url" in caplog.text
