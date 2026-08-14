"""Tests for V4-GCS-M1 — upload route replacement + object validation on job creation.

Verifies:
- POST /uploads/sign returns a GCS signed PUT URL (mocked SDK)
- POST /uploads/sign calls gcs_service.mint_signed_put_url with correct args
- PUT /dev/upload/{id} is removed (404)
- POST /jobs returns 400 when dataset does not exist in GCS
- POST /jobs returns 502 when GCS check fails (SDK error)
- POST /jobs succeeds when object_exists returns True
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.schemas.fe_contract import CreateJobResponse

HEADERS = {"Authorization": "Bearer dev-token-change-me", "Content-Type": "application/json"}


# ── POST /uploads/sign — real GCS signed URL ─────────────────────────────────


@pytest.mark.asyncio
async def test_sign_upload_returns_gcs_signed_url(client: AsyncClient) -> None:
    """POST /uploads/sign must call gcs_service and return a GCS V4 signed URL."""
    fake_url = "https://storage.googleapis.com/terafac-datasets/datasets/ds_abc/raw.zip?X-Goog-Signature=FAKE"
    with patch("src.routes.upload_routes.mint_signed_put_url", return_value=fake_url) as mock_mint:
        resp = await client.post("/uploads/sign", headers=HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["signed_put_url"] == fake_url
    assert body["object_path"].startswith("datasets/")
    assert body["object_path"].endswith("/raw.zip")
    # Verify correct args passed to gcs_service
    mock_mint.assert_called_once()
    call_kwargs = mock_mint.call_args[1]
    assert call_kwargs["content_type"] == "application/zip"
    assert call_kwargs["object_path"] == body["object_path"]


@pytest.mark.asyncio
async def test_sign_upload_generates_unique_dataset_ids(client: AsyncClient) -> None:
    """Two sequential calls must produce different object paths."""
    with patch(
        "src.routes.upload_routes.mint_signed_put_url",
        return_value="https://storage.googleapis.com/signed",
    ):
        r1 = await client.post("/uploads/sign", headers=HEADERS)
        r2 = await client.post("/uploads/sign", headers=HEADERS)

    assert r1.json()["object_path"] != r2.json()["object_path"]


# ── PUT /dev/upload/{id} removed ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dev_upload_endpoint_removed(client: AsyncClient) -> None:
    """PUT /dev/upload/{id} must no longer exist (V4 removed it)."""
    resp = await client.put("/dev/upload/ds_123", headers=HEADERS, content=b"fake-zip")
    # Either 404 or 405 (method not allowed) — endpoint should not exist
    assert resp.status_code in (404, 405)


# ── POST /jobs — object validation ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_job_rejects_missing_dataset(client: AsyncClient) -> None:
    """POST /jobs must return 400 when dataset_object_path does not exist in GCS."""
    with patch("src.routes.job_routes.object_exists", return_value=False):
        resp = await client.post(
            "/jobs",
            json={"prompt": "test", "dataset_object_path": "datasets/missing/raw.zip"},
            headers=HEADERS,
        )

    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_job_returns_502_on_gcs_error(client: AsyncClient) -> None:
    """POST /jobs must return 502 when GCS service raises an error."""
    from src.services.gcs_service import GCSServiceError

    with patch(
        "src.routes.job_routes.object_exists",
        side_effect=GCSServiceError("Network timeout"),
    ):
        resp = await client.post(
            "/jobs",
            json={"prompt": "test", "dataset_object_path": "datasets/ds_x/raw.zip"},
            headers=HEADERS,
        )

    assert resp.status_code == 502
    assert "unable to verify" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_job_succeeds_when_object_exists(client: AsyncClient) -> None:
    """POST /jobs must proceed to job creation when object_exists returns True."""
    mock_response = CreateJobResponse(job_id="job_gcs_001", stage="pre_masking")
    with (
        patch("src.routes.job_routes.object_exists", return_value=True),
        patch("src.routes.job_routes.job_service.create_job", return_value=mock_response),
        patch(
            "src.routes.job_routes.get_broker",
            return_value=AsyncMock(enqueue=AsyncMock()),
        ),
    ):
        resp = await client.post(
            "/jobs",
            json={"prompt": "gcs test", "dataset_object_path": "datasets/ds_ok/raw.zip"},
            headers=HEADERS,
        )

    assert resp.status_code == 201
    assert resp.json()["job_id"] == "job_gcs_001"
