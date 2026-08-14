from __future__ import annotations

import asyncio
import logging
import random
from concurrent.futures import ThreadPoolExecutor

from src.db.crud import update_doc
from src.schemas.job import JobStatus

logger = logging.getLogger(__name__)

COLLECTION = "jobs"

# ── Timing constants (seconds) — easy to override in tests via monkeypatch ────
PRE_MASKING_DELAY: float = 3.0
EPOCH_DELAY: float = 0.5
TOTAL_EPOCHS: int = 5

_executor = ThreadPoolExecutor(max_workers=2)


# ── Epoch metrics generator (matches MSW mock formula) ────────────────────────


def _epoch_metrics(epoch: int) -> dict:  # type: ignore[type-arg]
    """Return canned training metrics for a given epoch number.

    Formula mirrors the MSW handler in frontend/src/mocks/handlers.ts so the
    FE charts show the same curve shape when connected to the real backend.
    """
    return {
        "epoch": epoch,
        "loss_tr": round(1.0 - epoch * 0.08, 4),
        "loss_val": round(1.0 - epoch * 0.06, 4),
        "acc": round(0.5 + epoch * 0.04, 4),
        "iou": round(0.3 + epoch * 0.05, 4),
        "dice": round(0.4 + epoch * 0.045, 4),
    }


def _canned_final_metrics() -> dict:  # type: ignore[type-arg]
    """Final metrics written to the job doc when training completes (canned V1)."""
    return {
        "loss_val": 0.2143,
        "acc": 0.92,
        "iou": 0.78,
        "dice": 0.85,
        "epochs": TOTAL_EPOCHS,
        "total_minutes": 12,
    }


# ── Stage-advancement stubs ───────────────────────────────────────────────────


async def run_pre_masking(job_id: str) -> None:
    """Simulate the pre-masking stage.

    Waits PRE_MASKING_DELAY seconds (simulating a pretrained-checkpoint run),
    then advances the job to awaiting_annotation.
    """
    logger.info("Job %s: pre_masking started (%.1fs delay)", job_id, PRE_MASKING_DELAY)
    await asyncio.sleep(PRE_MASKING_DELAY)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor,
        update_doc,
        COLLECTION,
        job_id,
        {"status": JobStatus.awaiting_annotation.value},
    )
    logger.info("Job %s: -> awaiting_annotation", job_id)


async def run_training(job_id: str, gcs_urls: dict | None = None) -> None:  # type: ignore[type-arg]
    """Simulate a 5-epoch training run.

    For each epoch:
      - Sleeps EPOCH_DELAY seconds.
      - Updates Firestore with the current epoch number + canned metrics.

    After all epochs completes, advances the job to done and writes final
    metrics + canned sample predictions.

    Args:
        job_id: The Firestore job document ID.
        gcs_urls: Optional dict with signed GCS URLs (V4-GCS-M2). Keys:
            - dataset_signed_url: GET URL for the uploaded dataset zip
            - weights_signed_url: GET URL for base model weights
            - results_upload_url: PUT URL for uploading best.pt
            - results_metrics_url: PUT URL for uploading metrics.json
          In V4-VERTEX, the training agent will use these URLs to fetch data
          and upload results. In this stub, they are logged but not used.
    """
    from src.db.crud import get_doc

    # Log GCS URLs metadata (NEVER log the actual URL strings — they are secrets)
    if gcs_urls:
        url_keys = list(gcs_urls.keys())
        logger.info("Job %s: received GCS signed URLs: %s", job_id, url_keys)
    else:
        logger.info("Job %s: no GCS URLs provided (stub mode)", job_id)

    # Safety check: only run if job is actually in training stage
    doc = get_doc(COLLECTION, job_id)
    if doc and doc.get("status") != "training":
        logger.warning(
            "Job %s: training aborted (status=%s, not 'training')", job_id, doc.get("status")
        )
        return

    logger.info("Job %s: training started (%d epochs)", job_id, TOTAL_EPOCHS)

    epoch_metrics_list: list[dict] = []  # type: ignore[type-arg]
    loop = asyncio.get_event_loop()

    for epoch in range(1, TOTAL_EPOCHS + 1):
        await asyncio.sleep(EPOCH_DELAY)

        metrics = _epoch_metrics(epoch)
        epoch_metrics_list.append(metrics)

        payload = {
            "epoch": epoch,
            "epoch_metrics": epoch_metrics_list,
            "vram_used_mb": 18000 + random.randint(0, 2000),
            "gpu_util_pct": 70 + random.randint(0, 20),
        }
        await loop.run_in_executor(_executor, update_doc, COLLECTION, job_id, payload)
        logger.info("Job %s: epoch %d/%d complete", job_id, epoch, TOTAL_EPOCHS)

    # Training complete — write final state
    final_payload = {
        "status": JobStatus.done.value,
        "epoch": TOTAL_EPOCHS,
        "final_metrics": _canned_final_metrics(),
        "vram_used_mb": 0,
        "gpu_util_pct": 0,
    }
    await loop.run_in_executor(_executor, update_doc, COLLECTION, job_id, final_payload)
    logger.info("Job %s: -> done", job_id)
