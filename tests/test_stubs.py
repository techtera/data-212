from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from src.schemas.job import JobStatus
from src.services.stubs import (
    TOTAL_EPOCHS,
    _canned_final_metrics,
    _epoch_metrics,
    run_pre_masking,
    run_training,
)

# ── _epoch_metrics ────────────────────────────────────────────────────────────


def test_epoch_metrics_epoch_1() -> None:
    m = _epoch_metrics(1)
    assert m["epoch"] == 1
    assert m["loss_tr"] == round(1.0 - 1 * 0.08, 4)
    assert m["loss_val"] == round(1.0 - 1 * 0.06, 4)
    assert m["acc"] == round(0.5 + 1 * 0.04, 4)
    assert m["iou"] == round(0.3 + 1 * 0.05, 4)
    assert m["dice"] == round(0.4 + 1 * 0.045, 4)


def test_epoch_metrics_epoch_10() -> None:
    m = _epoch_metrics(10)
    assert m["epoch"] == 10
    # loss_tr should be 0.20 (1 - 10*0.08)
    assert m["loss_tr"] == round(1.0 - 10 * 0.08, 4)


def test_canned_final_metrics_keys() -> None:
    fm = _canned_final_metrics()
    for key in ("loss_val", "acc", "iou", "dice", "epochs", "total_minutes"):
        assert key in fm
    assert fm["epochs"] == TOTAL_EPOCHS


# ── run_pre_masking ───────────────────────────────────────────────────────────


async def test_run_pre_masking_updates_stage() -> None:
    """run_pre_masking must call update_doc with awaiting_annotation after sleeping."""
    with (
        patch("src.services.stubs.PRE_MASKING_DELAY", 0),  # no real sleep in tests
        patch("src.services.stubs.update_doc") as mock_update,
    ):
        await run_pre_masking("job-test-01")

    mock_update.assert_called_once_with(
        "jobs",
        "job-test-01",
        {"status": JobStatus.awaiting_annotation.value},
    )


async def test_run_pre_masking_uses_correct_collection() -> None:
    with (
        patch("src.services.stubs.PRE_MASKING_DELAY", 0),
        patch("src.services.stubs.update_doc") as mock_update,
    ):
        await run_pre_masking("job-xyz")

    args = mock_update.call_args[0]
    assert args[0] == "jobs"
    assert args[1] == "job-xyz"


async def test_run_pre_masking_sets_awaiting_annotation_not_training() -> None:
    """Must advance to awaiting_annotation, never jump straight to training."""
    with (
        patch("src.services.stubs.PRE_MASKING_DELAY", 0),
        patch("src.services.stubs.update_doc") as mock_update,
    ):
        await run_pre_masking("job-abc")

    payload = mock_update.call_args[0][2]
    assert payload["status"] == "awaiting_annotation"
    assert payload["status"] != "training"


# ── run_training ──────────────────────────────────────────────────────────────


async def test_run_training_calls_update_doc_per_epoch() -> None:
    """run_training must call update_doc once per epoch + once for the final state."""
    with (
        patch("src.services.stubs.EPOCH_DELAY", 0),
        patch("src.services.stubs.TOTAL_EPOCHS", 3),
        patch("src.services.stubs.update_doc") as mock_update,
    ):
        await run_training("job-train-01")

    # 3 epoch updates + 1 final = 4 total calls
    assert mock_update.call_count == 4


async def test_run_training_final_call_sets_done() -> None:
    """The last update_doc call must set status=done."""
    with (
        patch("src.services.stubs.EPOCH_DELAY", 0),
        patch("src.services.stubs.TOTAL_EPOCHS", 2),
        patch("src.services.stubs.update_doc") as mock_update,
    ):
        await run_training("job-train-02")

    final_payload = mock_update.call_args[0][2]
    assert final_payload["status"] == JobStatus.done.value
    assert "final_metrics" in final_payload
    assert final_payload["vram_used_mb"] == 0
    assert final_payload["gpu_util_pct"] == 0


async def test_run_training_epoch_increments() -> None:
    """Epoch counter in each update must match iteration order (1, 2, 3, ...)."""
    captured_epochs: list[int] = []

    def fake_update(collection: str, doc_id: str, data: dict) -> None:  # type: ignore[type-arg]
        if "epoch" in data and "status" not in data:
            captured_epochs.append(data["epoch"])

    with (
        patch("src.services.stubs.EPOCH_DELAY", 0),
        patch("src.services.stubs.TOTAL_EPOCHS", 3),
        patch("src.services.stubs.update_doc", side_effect=fake_update),
    ):
        await run_training("job-epochs")

    assert captured_epochs == [1, 2, 3]


async def test_run_training_final_metrics_structure() -> None:
    """Final metrics written to Firestore must contain all expected keys."""
    with (
        patch("src.services.stubs.EPOCH_DELAY", 0),
        patch("src.services.stubs.TOTAL_EPOCHS", 1),
        patch("src.services.stubs.update_doc") as mock_update,
    ):
        await run_training("job-fm")

    final_payload = mock_update.call_args[0][2]
    fm = final_payload["final_metrics"]
    for key in ("loss_val", "acc", "iou", "dice", "epochs", "total_minutes"):
        assert key in fm, f"missing key: {key}"


# ── Route integration: POST /jobs spawns background task ─────────────────────


async def test_create_job_route_spawns_pre_masking(
    client,  # type: ignore[no-untyped-def]
    auth_headers: dict,
) -> None:
    """POST /jobs must return 201 and enqueue a pre_masking BrokerTask via broker."""
    from src.schemas.fe_contract import CreateJobResponse

    mock_response = CreateJobResponse(job_id="job_bt_01", stage="pre_masking")
    mock_enqueue = AsyncMock()

    with (
        patch("src.routes.job_routes.job_service.create_job", return_value=mock_response),
        patch(
            "src.routes.job_routes.get_broker",
            return_value=AsyncMock(enqueue=mock_enqueue),
        ),
        patch("src.middleware.quota.query_docs", return_value=[]),
        patch("src.routes.job_routes.object_exists", return_value=True),
    ):
        resp = await client.post(
            "/jobs",
            json={"prompt": "train", "dataset_object_path": "datasets/x/raw.zip"},
            headers=auth_headers,
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"] == "job_bt_01"
    assert body["stage"] == "pre_masking"
    # Broker must have been called with the correct job_id and step
    mock_enqueue.assert_awaited_once()
    task = mock_enqueue.call_args[0][0]
    assert task.job_id == "job_bt_01"
    assert task.task_type == "pre_masking"


async def test_create_job_route_returns_201_before_task_finishes(
    client,  # type: ignore[no-untyped-def]
    auth_headers: dict,
) -> None:
    """HTTP 201 must be returned even when the broker enqueue yields."""
    from src.schemas.fe_contract import CreateJobResponse

    mock_response = CreateJobResponse(job_id="job_bt_02", stage="pre_masking")

    async def slow_enqueue(task):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0)  # yield but don't block

    with (
        patch("src.routes.job_routes.job_service.create_job", return_value=mock_response),
        patch(
            "src.routes.job_routes.get_broker",
            return_value=AsyncMock(enqueue=slow_enqueue),
        ),
        patch("src.middleware.quota.query_docs", return_value=[]),
        patch("src.routes.job_routes.object_exists", return_value=True),
    ):
        resp = await client.post(
            "/jobs",
            json={"prompt": "test", "dataset_object_path": "datasets/d/raw.zip"},
            headers=auth_headers,
        )

    assert resp.status_code == 201
