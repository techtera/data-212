from __future__ import annotations

import logging
import random
from datetime import UTC, datetime

from src.db.crud import get_doc
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

logger = logging.getLogger(__name__)

COLLECTION = "jobs"

# ── Canned constants ──────────────────────────────────────────────────────────

_VRAM_TOTAL_MB: float = 24_000.0
_QUOTA_JOBS: int = 18
_QUOTA_MINUTES: int = 480

_FLAGGED_IMAGES = [
    FlaggedImage(image_id="9", url="/mock-data/flagged/9.png"),
    FlaggedImage(image_id="10", url="/mock-data/flagged/10.png"),
    FlaggedImage(image_id="11", url="/mock-data/flagged/11.png"),
    FlaggedImage(image_id="12", url="/mock-data/flagged/12.png"),
]

_INFERENCE_CODE = """\
import torch
from PIL import Image
import numpy as np


def load_checkpoint(path: str):
    return torch.load(path, map_location="cpu")


def predict(image_path: str, model):
    img = np.array(Image.open(image_path).convert("RGB"))
    return np.zeros(img.shape[:2], dtype=np.uint8)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True)
    p.add_argument("--checkpoint", default="best.pt")
    args = p.parse_args()
    model = load_checkpoint(args.checkpoint)
    mask = predict(args.image, model)
    Image.fromarray(mask).save("pred_mask.png")
    print("saved pred_mask.png")
"""

_CANNED_SAMPLE_PREDS = [
    SamplePrediction(
        image_url="/mock-data/images/1.png",
        pred_mask_url="/mock-data/images/1.png",
        gt_mask_url="/mock-data/images/1.png",
    ),
    SamplePrediction(
        image_url="/mock-data/images/2.png",
        pred_mask_url="/mock-data/images/2.png",
        gt_mask_url="/mock-data/images/2.png",
    ),
    SamplePrediction(
        image_url="/mock-data/images/3.png",
        pred_mask_url="/mock-data/images/3.png",
        gt_mask_url="/mock-data/images/3.png",
    ),
]


# ── Public helpers ────────────────────────────────────────────────────────────


def _require_job(job_id: str) -> dict:  # type: ignore[type-arg]
    """Return the Firestore document for *job_id* or raise KeyError."""
    data = get_doc(COLLECTION, job_id)
    if data is None:
        raise KeyError(f"job {job_id} not found")
    return data


def get_flagged(job_id: str) -> list[FlaggedImage]:
    """Return the flagged-image list stored on the job doc (canned in V1)."""
    data = _require_job(job_id)
    raw = data.get("flagged_images", [])
    if raw:
        return [FlaggedImage(image_id=str(r["image_id"]), url=r["url"]) for r in raw]
    return list(_FLAGGED_IMAGES)


def get_data_preview(job_id: str) -> list[DataPreviewImage]:
    """Return 32 canned dataset-preview images (image-only, no masks)."""
    _require_job(job_id)  # raises KeyError if job doesn't exist
    return [
        DataPreviewImage(image_id=str(i), url=f"/mock-data/images/{i}.png") for i in range(1, 33)
    ]


def get_compute(job_id: str) -> ComputeSample:
    """Return live compute stats for the job.

    During training: randomised VRAM/GPU usage matching MSW mock range.
    Otherwise: zeros (no GPU active).
    """
    data = _require_job(job_id)
    stage = data.get("status", "error")
    now_iso = datetime.now(tz=UTC).isoformat()

    if stage == "training":
        vram_used = float(data.get("vram_used_mb") or (18_000 + random.randint(0, 2_000)))
        gpu_util = float(data.get("gpu_util_pct") or (70 + random.randint(0, 20)))
    else:
        vram_used = 0.0
        gpu_util = 0.0

    return ComputeSample(
        vram_used_mb=vram_used,
        vram_total_mb=_VRAM_TOTAL_MB,
        gpu_util_pct=gpu_util,
        quota_remaining_jobs=_QUOTA_JOBS,
        quota_remaining_minutes=_QUOTA_MINUTES,
        ts=now_iso,
    )


def get_logs(job_id: str) -> LogsResponse:
    """Return epoch metrics + log lines accumulated so far.

    Reads the epoch_metrics list written by run_training into the job doc.
    Falls back to a single placeholder line when training hasn't started yet.
    """
    data = _require_job(job_id)
    raw_epochs: list[dict] = data.get("epoch_metrics", [])  # type: ignore[type-arg]

    epochs = [
        EpochMetrics(
            epoch=e["epoch"],
            loss_tr=e["loss_tr"],
            loss_val=e["loss_val"],
            acc=e["acc"],
            iou=e["iou"],
            dice=e["dice"],
        )
        for e in raw_epochs
    ]

    lines: list[LogLine] = []
    now_iso = datetime.now(tz=UTC).isoformat()
    if epochs:
        for ep in epochs:
            lines.append(
                LogLine(
                    ts=now_iso,
                    level="info",
                    msg=(f"epoch {ep.epoch} loss={ep.loss_tr:.4f} val={ep.loss_val:.4f}"),
                )
            )
    else:
        lines.append(LogLine(ts=now_iso, level="info", msg="Waiting for training to start…"))

    return LogsResponse(lines=lines, epochs=epochs)


def get_results(job_id: str) -> ResultsResponse:
    """Return final training results (only meaningful after stage=done).

    Raises ValueError when the job is not yet done.
    """
    data = _require_job(job_id)
    stage = data.get("status", "error")
    if stage != "done":
        raise ValueError(f"job {job_id} results not available in stage '{stage}'")

    raw_fm: dict = data.get("final_metrics") or {}  # type: ignore[type-arg]
    fm = FinalMetrics(
        loss_val=raw_fm.get("loss_val", 0.2143),
        acc=raw_fm.get("acc", 0.92),
        iou=raw_fm.get("iou", 0.78),
        dice=raw_fm.get("dice", 0.85),
        epochs=int(raw_fm.get("epochs", 10)),
        total_minutes=float(raw_fm.get("total_minutes", 12)),
    )

    return ResultsResponse(
        final_metrics=fm,
        sample_predictions=_CANNED_SAMPLE_PREDS,
        risk_tier=data.get("risk_tier") or "medium",
        risk_reasoning=data.get("risk_reasoning") or "Stub: medium risk assumed (V1).",
    )


def get_inference(job_id: str) -> InferenceResponse:
    """Return the inference script + a stub checkpoint URL (V1).

    Raises ValueError when the job is not yet done.
    """
    data = _require_job(job_id)
    stage = data.get("status", "error")
    if stage != "done":
        raise ValueError(f"job {job_id} inference not available in stage '{stage}'")

    return InferenceResponse(
        code=_INFERENCE_CODE,
        checkpoint_signed_url="/mock-data/checkpoint-mock.pt",
    )
