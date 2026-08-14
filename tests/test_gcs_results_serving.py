"""Tests for V4-GCS-M3 — checkpoint + results serving via signed URLs.

Verifies:
- GET /jobs/{id}/inference returns a fresh GCS signed GET URL for the checkpoint
- GET /jobs/{id}/inference mints a new URL on each request (never cached/baked)
- GET /jobs/{id}/inference falls back to mock when GCS unavailable
- GET /jobs/{id}/results serves sample predictions from GCS signed URLs
- GET /jobs/{id}/results falls back to mock images when GCS unavailable
- Checkpoint URL is never logged
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

HEADERS = {"Authorization": "Bearer dev-token-change-me"}

_DONE_DOC = {
    "status": "done",
    "final_metrics": {
        "loss_val": 0.21,
        "acc": 0.92,
        "iou": 0.78,
        "dice": 0.85,
        "epochs": 5,
        "total_minutes": 12,
    },
    "risk_tier": "low",
    "risk_reasoning": "Low risk based on standard architecture.",
}


# ── GET /jobs/{id}/inference — signed checkpoint URL ──────────────────────────


@pytest.mark.asyncio
async def test_inference_returns_gcs_signed_checkpoint_url(client: AsyncClient) -> None:
    """GET /inference must return a fresh GCS signed GET URL for the checkpoint."""
    with (
        patch("src.services.data_service.get_doc", return_value=_DONE_DOC),
        patch(
            "src.services.data_service.mint_signed_get_url",
            return_value="https://storage.googleapis.com/terafac-datasets/results/job_001/best.pt?X-Goog-Signature=FRESH",
        ) as mock_mint,
    ):
        resp = await client.get("/jobs/job_001/inference", headers=HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert "storage.googleapis.com" in body["checkpoint_signed_url"]
    assert "X-Goog-Signature" in body["checkpoint_signed_url"]
    mock_mint.assert_called_once_with("results/job_001/best.pt")


@pytest.mark.asyncio
async def test_inference_mints_fresh_url_each_request(client: AsyncClient) -> None:
    """Each call to GET /inference must mint a fresh URL (never cached)."""
    call_count = 0

    def unique_url(path):
        nonlocal call_count
        call_count += 1
        return f"https://storage.googleapis.com/signed-{call_count}"

    with (
        patch("src.services.data_service.get_doc", return_value=_DONE_DOC),
        patch("src.services.data_service.mint_signed_get_url", side_effect=unique_url),
    ):
        r1 = await client.get("/jobs/job_001/inference", headers=HEADERS)
        r2 = await client.get("/jobs/job_001/inference", headers=HEADERS)

    # Two different URLs from two requests
    assert r1.json()["checkpoint_signed_url"] != r2.json()["checkpoint_signed_url"]
    assert call_count >= 2  # Called at least twice (once per request, plus results samples)


@pytest.mark.asyncio
async def test_inference_falls_back_to_mock_on_gcs_error(client: AsyncClient) -> None:
    """If GCS is unavailable, fall back to the mock checkpoint path."""
    from src.services.gcs_service import GCSServiceError

    with (
        patch("src.services.data_service.get_doc", return_value=_DONE_DOC),
        patch(
            "src.services.data_service.mint_signed_get_url",
            side_effect=GCSServiceError("SA key missing"),
        ),
    ):
        resp = await client.get("/jobs/job_001/inference", headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["checkpoint_signed_url"] == "/mock-data/checkpoint-mock.pt"


@pytest.mark.asyncio
async def test_inference_not_available_before_done(client: AsyncClient) -> None:
    """GET /inference must return 409 when job is not in done stage."""
    with patch("src.services.data_service.get_doc", return_value={"status": "training"}):
        resp = await client.get("/jobs/job_001/inference", headers=HEADERS)
    assert resp.status_code == 409


# ── GET /jobs/{id}/results — sample predictions from GCS ──────────────────────


@pytest.mark.asyncio
async def test_results_serves_gcs_signed_image_urls(client: AsyncClient) -> None:
    """GET /results must return sample predictions with GCS signed URLs."""
    call_count = 0

    def mock_signed_url(path):
        nonlocal call_count
        call_count += 1
        return f"https://storage.googleapis.com/{path}?signed={call_count}"

    with (
        patch("src.services.data_service.get_doc", return_value=_DONE_DOC),
        patch("src.services.data_service.mint_signed_get_url", side_effect=mock_signed_url),
    ):
        resp = await client.get("/jobs/job_001/results", headers=HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    preds = body["sample_predictions"]
    assert len(preds) == 3
    # Each prediction should have signed GCS URLs
    for pred in preds:
        assert "storage.googleapis.com" in pred["image_url"]
        assert "storage.googleapis.com" in pred["pred_mask_url"]
        assert "storage.googleapis.com" in pred["gt_mask_url"]


@pytest.mark.asyncio
async def test_results_falls_back_to_mock_on_gcs_error(client: AsyncClient) -> None:
    """If GCS is unavailable, results should fall back to mock images."""
    from src.services.gcs_service import GCSServiceError

    with (
        patch("src.services.data_service.get_doc", return_value=_DONE_DOC),
        patch(
            "src.services.data_service.mint_signed_get_url",
            side_effect=GCSServiceError("Network error"),
        ),
    ):
        resp = await client.get("/jobs/job_001/results", headers=HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    preds = body["sample_predictions"]
    # Fallback to mock images
    assert "/mock-data/images/" in preds[0]["image_url"]


# ── Security: signed URLs never in logs ───────────────────────────────────────


@pytest.mark.asyncio
async def test_inference_url_not_logged(client: AsyncClient, caplog) -> None:
    """The signed checkpoint URL must NEVER appear in server logs."""
    import logging

    secret_url = "https://storage.googleapis.com/terafac-datasets/SECRET-CHECKPOINT-TOKEN"

    with (
        caplog.at_level(logging.DEBUG),
        patch("src.services.data_service.get_doc", return_value=_DONE_DOC),
        patch("src.services.data_service.mint_signed_get_url", return_value=secret_url),
    ):
        await client.get("/jobs/job_001/inference", headers=HEADERS)

    assert "SECRET-CHECKPOINT-TOKEN" not in caplog.text
