from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

"""End-to-end integration test for the TERAFAC V1 backend.

Exercises the full happy-path flow:
  login → sign upload → create job → poll (pre_masking)
  → (stub advances) → poll (awaiting_annotation) → submit annotations
  → poll (awaiting_approval) → approve → poll (training)
  → (stub advances) → poll (done) → results → inference
  → rerun (new job) → reject alternative path

All Firestore calls are mocked at the service/crud layer — no real
database connection is required to run these tests.  The test client
hits the real FastAPI router layer so routing, auth, schema validation,
and status codes are all exercised.

Tests are intentionally kept deterministic — no asyncio.sleep() calls,
no background-task race conditions.  Background tasks are intercepted
via patch so they run synchronously inside the test.
"""

# ── Fixtures / helpers ────────────────────────────────────────────────────────

AUTH = {"Authorization": "Bearer dev-token-change-me"}
JSON = {"Content-Type": "application/json"}
HEADERS = {**AUTH, **JSON}

_BASE_DOC = {
    "prompt": "integration test job",
    "dataset_object_path": "datasets/ds_int/raw.zip",
    "status": "pre_masking",
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
    "created_at": "2026-08-11T10:00:00+00:00",
    "updated_at": "2026-08-11T10:00:00+00:00",
}


def _doc(**overrides):  # type: ignore[no-untyped-def]
    return {**_BASE_DOC, **overrides}


# ── 1. Health check ───────────────────────────────────────────────────────────


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── 2. Auth: login + logout ───────────────────────────────────────────────────


async def test_login_returns_token(client: AsyncClient) -> None:
    """V2: login accepts email + password and returns a session token."""
    fake_user = {
        "id": "user_int_001",
        "email": "admin@terafac.dev",
        "password_hash": "",
        "is_active": True,
    }
    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=fake_user),
        patch("src.services.auth_service.verify_password", return_value=True),
        patch("src.db.sessions.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.set.return_value = None
        resp = await client.post(
            "/auth/login", json={"email": "admin@terafac.dev", "password": "adminpass1"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "expires_in" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_creds_rejected(client: AsyncClient) -> None:
    """V2: wrong credentials return 401 regardless of whether user exists."""
    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=None):
        resp = await client.post(
            "/auth/login", json={"email": "nobody@terafac.dev", "password": "wrongpass"}
        )
    assert resp.status_code == 401


async def test_logout_204(client: AsyncClient) -> None:
    resp = await client.post("/auth/logout", headers=AUTH)
    assert resp.status_code == 204


# ── 3. Upload sign + dev acceptor ─────────────────────────────────────────────


async def test_sign_upload_and_dev_put(client: AsyncClient) -> None:
    """Full two-hop upload dance: sign → PUT to the returned URL."""
    # Step 1: get signed URL
    resp = await client.post("/uploads/sign", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    signed_url: str = body["signed_put_url"]
    object_path: str = body["object_path"]

    assert object_path.startswith("datasets/")
    assert object_path.endswith("/raw.zip")
    assert "dev/upload" in signed_url

    # Step 2: PUT bytes to the dev acceptor (strip scheme+host — test client is base-relative)
    from urllib.parse import urlparse

    path = urlparse(signed_url).path
    put_resp = await client.put(path, headers=AUTH, content=b"fake-zip-bytes")
    assert put_resp.status_code == 200
    assert put_resp.json()["ok"] == "accepted"


# ── 4. Create job ─────────────────────────────────────────────────────────────


async def test_create_job_returns_pre_masking(client: AsyncClient) -> None:
    with (
        patch("src.services.job_service.create_doc", return_value="job_int_001"),
        patch("src.services.job_service.get_doc", return_value=_doc()),
        patch("src.routes.job_routes.stubs.run_pre_masking"),  # don't actually sleep
    ):
        resp = await client.post(
            "/jobs",
            json={
                "prompt": "integration test job",
                "dataset_object_path": "datasets/ds_int/raw.zip",
            },
            headers=HEADERS,
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"] == "job_int_001"
    assert body["stage"] == "pre_masking"


# ── 5. Poll job — pre_masking ─────────────────────────────────────────────────


async def test_get_job_pre_masking(client: AsyncClient) -> None:
    with patch("src.services.job_service.get_doc", return_value=_doc(status="pre_masking")):
        resp = await client.get("/jobs/job_int_001", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "pre_masking"
    assert body["progress"] == 25
    assert body["flagged"] is None


# ── 6. Poll job — awaiting_annotation ────────────────────────────────────────


async def test_get_job_awaiting_annotation(client: AsyncClient) -> None:
    with patch(
        "src.services.job_service.get_doc",
        return_value=_doc(status="awaiting_annotation"),
    ):
        resp = await client.get("/jobs/job_int_001", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "awaiting_annotation"
    assert body["progress"] == 50
    assert len(body["flagged"]) == 4
    assert body["unannotated_count"] == 4


# ── 7. Get flagged images ─────────────────────────────────────────────────────


async def test_get_flagged_images(client: AsyncClient) -> None:
    with patch(
        "src.services.data_service.get_doc",
        return_value=_doc(status="awaiting_annotation"),
    ):
        resp = await client.get("/jobs/job_int_001/flagged", headers=AUTH)

    assert resp.status_code == 200
    images = resp.json()
    assert len(images) == 4
    assert images[0]["image_id"] == "9"


# ── 8. Get data preview ───────────────────────────────────────────────────────


async def test_get_data_preview_32_images(client: AsyncClient) -> None:
    with patch(
        "src.services.data_service.get_doc",
        return_value=_doc(status="awaiting_annotation"),
    ):
        resp = await client.get("/jobs/job_int_001/data-preview", headers=AUTH)

    assert resp.status_code == 200
    images = resp.json()
    assert len(images) == 32


# ── 9. Submit annotations → awaiting_approval ─────────────────────────────────


async def test_submit_annotations(client: AsyncClient) -> None:
    with (
        patch(
            "src.services.job_service.get_doc",
            return_value=_doc(status="awaiting_annotation"),
        ),
        patch("src.services.job_service.update_doc"),
    ):
        resp = await client.post(
            "/jobs/job_int_001/annotations",
            json={"ack": True},
            headers=HEADERS,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stage"] == "awaiting_approval"


# ── 10. Poll job — awaiting_approval ──────────────────────────────────────────


async def test_get_job_awaiting_approval(client: AsyncClient) -> None:
    with patch(
        "src.services.job_service.get_doc",
        return_value=_doc(status="awaiting_approval", risk_tier="medium"),
    ):
        resp = await client.get("/jobs/job_int_001", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "awaiting_approval"
    assert body["progress"] == 75


# ── 11. Approve → training ────────────────────────────────────────────────────


async def test_approve_job(client: AsyncClient) -> None:
    with (
        patch(
            "src.services.job_service.get_doc",
            return_value=_doc(status="awaiting_approval"),
        ),
        patch("src.services.job_service.update_doc"),
        patch("src.routes.job_action_routes.stubs.run_training"),  # don't sleep
    ):
        resp = await client.post("/jobs/job_int_001/approve", headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["stage"] == "training"


# ── 12. Poll job — training with epoch ────────────────────────────────────────


async def test_get_job_training_with_epoch(client: AsyncClient) -> None:
    with patch(
        "src.services.job_service.get_doc",
        return_value=_doc(status="training", epoch=5),
    ):
        resp = await client.get("/jobs/job_int_001", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "training"
    assert body["epoch"] == 5
    assert body["progress"] == 50  # 5/10 * 100


# ── 13. Compute during training ───────────────────────────────────────────────


async def test_get_compute_during_training(client: AsyncClient) -> None:
    with patch(
        "src.services.data_service.get_doc",
        return_value=_doc(status="training", vram_used_mb=19000, gpu_util_pct=82),
    ):
        resp = await client.get("/jobs/job_int_001/compute", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert body["vram_used_mb"] == 19000.0
    assert body["gpu_util_pct"] == 82.0
    assert body["vram_total_mb"] == 24000.0


# ── 14. Logs during training ──────────────────────────────────────────────────


async def test_get_logs_during_training(client: AsyncClient) -> None:
    epoch_metrics = [
        {
            "epoch": i,
            "loss_tr": round(1.0 - i * 0.08, 4),
            "loss_val": round(1.0 - i * 0.06, 4),
            "acc": round(0.5 + i * 0.04, 4),
            "iou": round(0.3 + i * 0.05, 4),
            "dice": round(0.4 + i * 0.045, 4),
        }
        for i in range(1, 6)
    ]
    with patch(
        "src.services.data_service.get_doc",
        return_value=_doc(status="training", epoch_metrics=epoch_metrics),
    ):
        resp = await client.get("/jobs/job_int_001/logs", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["epochs"]) == 5
    assert len(body["lines"]) == 5
    assert body["epochs"][0]["epoch"] == 1


# ── 15. Results not available before done ─────────────────────────────────────


async def test_get_results_before_done_returns_409(client: AsyncClient) -> None:
    with patch(
        "src.services.data_service.get_doc",
        return_value=_doc(status="training"),
    ):
        resp = await client.get("/jobs/job_int_001/results", headers=AUTH)

    assert resp.status_code == 409


# ── 16. Poll job — done ───────────────────────────────────────────────────────


async def test_get_job_done(client: AsyncClient) -> None:
    with patch(
        "src.services.job_service.get_doc",
        return_value=_doc(status="done"),
    ):
        resp = await client.get("/jobs/job_int_001", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "done"
    assert body["progress"] == 100


# ── 17. Results after done ────────────────────────────────────────────────────


async def test_get_results_after_done(client: AsyncClient) -> None:
    done_doc = _doc(
        status="done",
        final_metrics={
            "loss_val": 0.2143,
            "acc": 0.92,
            "iou": 0.78,
            "dice": 0.85,
            "epochs": 10,
            "total_minutes": 12,
        },
        risk_tier="medium",
        risk_reasoning="Stub: medium risk assumed.",
    )
    with patch("src.services.data_service.get_doc", return_value=done_doc):
        resp = await client.get("/jobs/job_int_001/results", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_tier"] == "medium"
    assert body["final_metrics"]["acc"] == 0.92
    assert len(body["sample_predictions"]) == 3


# ── 18. Inference after done ──────────────────────────────────────────────────


async def test_get_inference_after_done(client: AsyncClient) -> None:
    with patch("src.services.data_service.get_doc", return_value=_doc(status="done")):
        resp = await client.get("/jobs/job_int_001/inference", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert "torch" in body["code"]
    assert "checkpoint" in body["checkpoint_signed_url"]


# ── 19. Reject alternative path ───────────────────────────────────────────────


async def test_reject_job(client: AsyncClient) -> None:
    with (
        patch(
            "src.services.job_service.get_doc",
            return_value=_doc(status="awaiting_approval"),
        ),
        patch("src.services.job_service.update_doc"),
    ):
        resp = await client.post("/jobs/job_int_001/reject", headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["stage"] == "rejected"


# ── 20. Rerun from terminal state ─────────────────────────────────────────────


async def test_rerun_job(client: AsyncClient) -> None:
    with (
        patch(
            "src.services.job_service.get_doc",
            return_value=_doc(status="done"),
        ),
        patch("src.services.job_service.create_doc", return_value="job_int_002"),
        patch("src.routes.job_action_routes.stubs.run_pre_masking"),
    ):
        resp = await client.post("/jobs/job_int_001/rerun", headers=HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["new_job_id"] == "job_int_002"
    assert body["stage"] == "pre_masking"


# ── 21. List jobs ─────────────────────────────────────────────────────────────


async def test_list_jobs(client: AsyncClient) -> None:
    docs = [
        {
            "id": "job_int_001",
            "prompt": "integration test job",
            "status": "done",
            "risk_tier": "medium",
            "created_at": "2026-08-11T10:00:00+00:00",
        }
    ]
    with patch("src.services.job_service.query_docs", return_value=docs):
        resp = await client.get("/jobs", headers=AUTH)

    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "job_int_001"
    assert jobs[0]["stage"] == "done"


# ── 22. 401 on every protected route without token ───────────────────────────


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/jobs"),
        ("GET", "/jobs/x"),
        ("POST", "/jobs"),
        ("POST", "/uploads/sign"),
        ("GET", "/jobs/x/flagged"),
        ("GET", "/jobs/x/data-preview"),
        ("GET", "/jobs/x/compute"),
        ("GET", "/jobs/x/logs"),
        ("GET", "/jobs/x/results"),
        ("GET", "/jobs/x/inference"),
        ("POST", "/jobs/x/annotations"),
        ("POST", "/jobs/x/approve"),
        ("POST", "/jobs/x/reject"),
        ("POST", "/jobs/x/rerun"),
        ("POST", "/auth/logout"),
    ],
)
async def test_all_protected_routes_require_auth(
    client: AsyncClient, method: str, path: str
) -> None:
    resp = await client.request(method, path)
    assert resp.status_code == 401, f"{method} {path} returned {resp.status_code}, expected 401"


# ── 23. 404 for unknown job on every data endpoint ───────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/jobs/ghost",
        "/jobs/ghost/flagged",
        "/jobs/ghost/data-preview",
        "/jobs/ghost/compute",
        "/jobs/ghost/logs",
    ],
)
async def test_unknown_job_returns_404(client: AsyncClient, path: str) -> None:
    with (
        patch("src.services.job_service.get_doc", return_value=None),
        patch("src.services.data_service.get_doc", return_value=None),
    ):
        resp = await client.get(path, headers=AUTH)
    assert resp.status_code == 404


# ── 24. Stage guard: wrong-stage returns 409 ──────────────────────────────────


async def test_annotations_on_pre_masking_returns_409(client: AsyncClient) -> None:
    with patch(
        "src.services.job_service.get_doc",
        return_value=_doc(status="pre_masking"),
    ):
        resp = await client.post(
            "/jobs/job_int_001/annotations",
            json={"ack": True},
            headers=HEADERS,
        )
    assert resp.status_code == 409


async def test_approve_on_training_returns_409(client: AsyncClient) -> None:
    with patch(
        "src.services.job_service.get_doc",
        return_value=_doc(status="training"),
    ):
        resp = await client.post("/jobs/job_int_001/approve", headers=HEADERS)
    assert resp.status_code == 409


async def test_rerun_on_active_job_returns_409(client: AsyncClient) -> None:
    with patch(
        "src.services.job_service.get_doc",
        return_value=_doc(status="training"),
    ):
        resp = await client.post("/jobs/job_int_001/rerun", headers=HEADERS)
    assert resp.status_code == 409
