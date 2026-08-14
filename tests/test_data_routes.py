from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from httpx import AsyncClient

from src.schemas.fe_contract import (
    ComputeSample,
    DataPreviewImage,
    EpochMetrics,
    FinalMetrics,
    FlaggedImage,
    InferenceResponse,
    LogLine,
    LogsResponse,
    ResultsResponse,
    SamplePrediction,
)

_NOW = datetime.now(tz=UTC).isoformat()

# ── POST /uploads/sign ────────────────────────────────────────────────────────


@patch(
    "src.routes.upload_routes.mint_signed_put_url",
    return_value="https://storage.googleapis.com/terafac-datasets/datasets/ds_test/raw.zip?X-Goog-Signature=FAKE",
)
async def test_sign_upload_returns_200(mock_mint, client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post("/uploads/sign", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "signed_put_url" in body
    assert "object_path" in body
    assert body["object_path"].startswith("datasets/")
    assert body["object_path"].endswith("/raw.zip")
    assert "storage.googleapis.com" in body["signed_put_url"]
    mock_mint.assert_called_once()


async def test_sign_upload_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.post("/uploads/sign")
    assert resp.status_code == 401


@patch(
    "src.routes.upload_routes.mint_signed_put_url",
    return_value="https://storage.googleapis.com/signed",
)
async def test_sign_upload_different_ids_each_call(
    mock_mint, client: AsyncClient, auth_headers: dict
) -> None:
    """Each call must generate a unique object_path."""
    r1 = await client.post("/uploads/sign", headers=auth_headers)
    r2 = await client.post("/uploads/sign", headers=auth_headers)
    assert r1.json()["object_path"] != r2.json()["object_path"]


# ── POST /auth/login ──────────────────────────────────────────────────────────


async def test_login_valid_credentials_returns_token(client: AsyncClient, settings) -> None:
    """V2: login with email+password returns access_token."""
    fake_user = {
        "id": "user_data_test",
        "email": "admin@terafac.dev",
        "password_hash": "",
        "is_active": True,
    }
    from unittest.mock import MagicMock, patch

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.set.return_value = None
    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=fake_user),
        patch("src.services.auth_service.verify_password", return_value=True),
        patch("src.db.sessions.db", mock_db),
    ):
        resp = await client.post(
            "/auth/login",
            json={"email": "admin@terafac.dev", "password": "adminpass1"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "expires_in" in body


async def test_login_wrong_password_returns_401(client: AsyncClient, settings) -> None:
    from unittest.mock import patch

    fake_user = {
        "id": "user_data_test",
        "email": "admin@terafac.dev",
        "password_hash": "",
        "is_active": True,
    }
    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=fake_user),
        patch("src.services.auth_service.verify_password", return_value=False),
    ):
        resp = await client.post(
            "/auth/login",
            json={"email": "admin@terafac.dev", "password": "wrong-password"},
        )
    assert resp.status_code == 401


async def test_login_wrong_username_returns_401(client: AsyncClient, settings) -> None:
    """V2: unknown email returns 401 (same as wrong password — no enumeration)."""
    from unittest.mock import patch

    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=None):
        resp = await client.post(
            "/auth/login",
            json={"email": "nobody@terafac.dev", "password": "anypassword"},
        )
    assert resp.status_code == 401


async def test_login_no_auth_header_required(client: AsyncClient, settings) -> None:
    """Login endpoint must NOT require a Bearer token (it IS the token-issuing endpoint)."""
    fake_user = {
        "id": "user_data_test",
        "email": "admin@terafac.dev",
        "password_hash": "",
        "is_active": True,
    }
    from unittest.mock import MagicMock, patch

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.set.return_value = None
    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=fake_user),
        patch("src.services.auth_service.verify_password", return_value=True),
        patch("src.db.sessions.db", mock_db),
    ):
        resp = await client.post(
            "/auth/login",
            json={"email": "admin@terafac.dev", "password": "adminpass1"},
        )
    assert resp.status_code == 200


# ── POST /auth/logout ─────────────────────────────────────────────────────────


async def test_logout_returns_204(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post("/auth/logout", headers=auth_headers)
    assert resp.status_code == 204


async def test_logout_no_auth_returns_401(client: AsyncClient) -> None:
    # logout is a no-op in V1 but still requires auth
    resp = await client.post("/auth/logout")
    assert resp.status_code == 401


# ── GET /jobs/{id}/flagged ────────────────────────────────────────────────────


async def test_get_flagged_returns_list(client: AsyncClient, auth_headers: dict) -> None:
    flagged = [FlaggedImage(image_id="9", url="/mock-data/flagged/9.png")]
    with patch("src.routes.data_routes.data_service.get_flagged", return_value=flagged):
        resp = await client.get("/jobs/job_001/flagged", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["image_id"] == "9"


async def test_get_flagged_unknown_job_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.data_routes.data_service.get_flagged",
        side_effect=KeyError("not found"),
    ):
        resp = await client.get("/jobs/ghost/flagged", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_flagged_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/jobs/job_001/flagged")
    assert resp.status_code == 401


# ── GET /jobs/{id}/data-preview ───────────────────────────────────────────────


async def test_get_data_preview_returns_32_images(client: AsyncClient, auth_headers: dict) -> None:
    preview = [
        DataPreviewImage(image_id=str(i), url=f"/mock-data/images/{i}.png") for i in range(1, 33)
    ]
    with patch("src.routes.data_routes.data_service.get_data_preview", return_value=preview):
        resp = await client.get("/jobs/job_001/data-preview", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 32


async def test_get_data_preview_unknown_job_returns_404(
    client: AsyncClient, auth_headers: dict
) -> None:
    with patch(
        "src.routes.data_routes.data_service.get_data_preview",
        side_effect=KeyError("not found"),
    ):
        resp = await client.get("/jobs/ghost/data-preview", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_data_preview_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/jobs/job_001/data-preview")
    assert resp.status_code == 401


# ── GET /jobs/{id}/compute ────────────────────────────────────────────────────


async def test_get_compute_returns_sample(client: AsyncClient, auth_headers: dict) -> None:
    sample = ComputeSample(
        vram_used_mb=18500.0,
        vram_total_mb=24000.0,
        gpu_util_pct=75.0,
        quota_remaining_jobs=18,
        quota_remaining_minutes=480,
        ts=_NOW,
    )
    with patch("src.routes.data_routes.data_service.get_compute", return_value=sample):
        resp = await client.get("/jobs/job_001/compute", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["vram_total_mb"] == 24000.0
    assert body["quota_remaining_jobs"] == 18


async def test_get_compute_unknown_job_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.data_routes.data_service.get_compute",
        side_effect=KeyError("not found"),
    ):
        resp = await client.get("/jobs/ghost/compute", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_compute_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/jobs/job_001/compute")
    assert resp.status_code == 401


# ── GET /jobs/{id}/logs ───────────────────────────────────────────────────────


async def test_get_logs_returns_lines_and_epochs(client: AsyncClient, auth_headers: dict) -> None:
    logs = LogsResponse(
        lines=[LogLine(ts=_NOW, level="info", msg="epoch 1 loss=0.92")],
        epochs=[EpochMetrics(epoch=1, loss_tr=0.92, loss_val=0.94, acc=0.54, iou=0.35, dice=0.44)],
    )
    with patch("src.routes.data_routes.data_service.get_logs", return_value=logs):
        resp = await client.get("/jobs/job_001/logs", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["lines"]) == 1
    assert len(body["epochs"]) == 1
    assert body["epochs"][0]["epoch"] == 1


async def test_get_logs_unknown_job_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.data_routes.data_service.get_logs",
        side_effect=KeyError("not found"),
    ):
        resp = await client.get("/jobs/ghost/logs", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_logs_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/jobs/job_001/logs")
    assert resp.status_code == 401


# ── GET /jobs/{id}/results ────────────────────────────────────────────────────


async def test_get_results_returns_200_when_done(client: AsyncClient, auth_headers: dict) -> None:
    results = ResultsResponse(
        final_metrics=FinalMetrics(
            loss_val=0.2143, acc=0.92, iou=0.78, dice=0.85, epochs=10, total_minutes=12
        ),
        sample_predictions=[
            SamplePrediction(
                image_url="/mock-data/images/1.png",
                pred_mask_url="/mock-data/images/1.png",
                gt_mask_url="/mock-data/images/1.png",
            )
        ],
        risk_tier="medium",
        risk_reasoning="Stub reasoning",
    )
    with patch("src.routes.data_routes.data_service.get_results", return_value=results):
        resp = await client.get("/jobs/job_001/results", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_tier"] == "medium"
    assert body["final_metrics"]["acc"] == 0.92
    assert len(body["sample_predictions"]) == 1


async def test_get_results_not_done_returns_409(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.data_routes.data_service.get_results",
        side_effect=ValueError("results not available in stage 'training'"),
    ):
        resp = await client.get("/jobs/job_001/results", headers=auth_headers)
    assert resp.status_code == 409


async def test_get_results_unknown_job_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.data_routes.data_service.get_results",
        side_effect=KeyError("not found"),
    ):
        resp = await client.get("/jobs/ghost/results", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_results_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/jobs/job_001/results")
    assert resp.status_code == 401


# ── GET /jobs/{id}/inference ──────────────────────────────────────────────────


async def test_get_inference_returns_code_and_url(client: AsyncClient, auth_headers: dict) -> None:
    inf = InferenceResponse(
        code="import torch\n",
        checkpoint_signed_url="/mock-data/checkpoint-mock.pt",
    )
    with patch("src.routes.data_routes.data_service.get_inference", return_value=inf):
        resp = await client.get("/jobs/job_001/inference", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "import torch" in body["code"]
    assert body["checkpoint_signed_url"] == "/mock-data/checkpoint-mock.pt"


async def test_get_inference_not_done_returns_409(client: AsyncClient, auth_headers: dict) -> None:
    with patch(
        "src.routes.data_routes.data_service.get_inference",
        side_effect=ValueError("inference not available in stage 'training'"),
    ):
        resp = await client.get("/jobs/job_001/inference", headers=auth_headers)
    assert resp.status_code == 409


async def test_get_inference_unknown_job_returns_404(
    client: AsyncClient, auth_headers: dict
) -> None:
    with patch(
        "src.routes.data_routes.data_service.get_inference",
        side_effect=KeyError("not found"),
    ):
        resp = await client.get("/jobs/ghost/inference", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_inference_no_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/jobs/job_001/inference")
    assert resp.status_code == 401


# ── data_service unit tests (no HTTP) ────────────────────────────────────────


def test_service_get_flagged_returns_canned_when_no_doc_images() -> None:
    from src.services.data_service import get_flagged

    with patch("src.services.data_service.get_doc", return_value={"status": "awaiting_annotation"}):
        result = get_flagged("job_001")

    assert len(result) == 4
    assert all(hasattr(f, "image_id") for f in result)


def test_service_get_data_preview_returns_32() -> None:
    from src.services.data_service import get_data_preview

    with patch("src.services.data_service.get_doc", return_value={"status": "training"}):
        result = get_data_preview("job_001")

    assert len(result) == 32
    assert result[0].image_id == "1"
    assert result[31].image_id == "32"


def test_service_get_compute_zeros_when_not_training() -> None:
    from src.services.data_service import get_compute

    with patch(
        "src.services.data_service.get_doc",
        return_value={"status": "awaiting_annotation"},
    ):
        result = get_compute("job_001")

    assert result.vram_used_mb == 0.0
    assert result.gpu_util_pct == 0.0
    assert result.vram_total_mb == 24_000.0


def test_service_get_compute_nonzero_when_training() -> None:
    from src.services.data_service import get_compute

    doc = {"status": "training", "vram_used_mb": 19000, "gpu_util_pct": 85}
    with patch("src.services.data_service.get_doc", return_value=doc):
        result = get_compute("job_001")

    assert result.vram_used_mb == 19000.0
    assert result.gpu_util_pct == 85.0


def test_service_get_logs_empty_epochs_returns_placeholder() -> None:
    from src.services.data_service import get_logs

    with patch(
        "src.services.data_service.get_doc",
        return_value={"status": "training", "epoch_metrics": []},
    ):
        result = get_logs("job_001")

    assert len(result.epochs) == 0
    assert len(result.lines) == 1
    assert "Waiting" in result.lines[0].msg


def test_service_get_logs_populated_epochs() -> None:
    from src.services.data_service import get_logs

    raw = [
        {"epoch": 1, "loss_tr": 0.92, "loss_val": 0.94, "acc": 0.54, "iou": 0.35, "dice": 0.44},
        {"epoch": 2, "loss_tr": 0.84, "loss_val": 0.88, "acc": 0.58, "iou": 0.40, "dice": 0.49},
    ]
    with patch(
        "src.services.data_service.get_doc",
        return_value={"status": "training", "epoch_metrics": raw},
    ):
        result = get_logs("job_001")

    assert len(result.epochs) == 2
    assert len(result.lines) == 2
    assert result.epochs[1].epoch == 2


def test_service_get_results_raises_when_not_done() -> None:
    import pytest

    from src.services.data_service import get_results

    with (
        patch(
            "src.services.data_service.get_doc",
            return_value={"status": "training"},
        ),
        pytest.raises(ValueError, match="training"),
    ):
        get_results("job_001")


def test_service_get_results_returns_data_when_done() -> None:
    from src.services.data_service import get_results

    doc = {
        "status": "done",
        "final_metrics": {
            "loss_val": 0.21,
            "acc": 0.91,
            "iou": 0.77,
            "dice": 0.84,
            "epochs": 10,
            "total_minutes": 12,
        },
        "risk_tier": "low",
        "risk_reasoning": "low risk",
    }
    with patch("src.services.data_service.get_doc", return_value=doc):
        result = get_results("job_001")

    assert result.final_metrics.acc == 0.91
    assert result.risk_tier == "low"
    assert len(result.sample_predictions) == 3


def test_service_get_inference_raises_when_not_done() -> None:
    import pytest

    from src.services.data_service import get_inference

    with (
        patch("src.services.data_service.get_doc", return_value={"status": "training"}),
        pytest.raises(ValueError, match="training"),
    ):
        get_inference("job_001")


def test_service_get_inference_returns_code_when_done() -> None:
    from src.services.data_service import get_inference

    with patch("src.services.data_service.get_doc", return_value={"status": "done"}):
        result = get_inference("job_001")

    assert "torch" in result.code
    assert result.checkpoint_signed_url != ""
