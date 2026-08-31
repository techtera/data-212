"""Coding agent — inference script generation and debugging."""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import require_auth
from .config import settings
from .db import execute
from .gcs import _get_bucket
from .coding_training import _call_gemini, _strip_markdown, _load_template

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coding", tags=["coding-inference"])

VM_INFERENCE_CONTEXT = """
The inference script runs on a GPU VM via this bash wrapper:
1. Script downloaded to $JOB_DIR/script.py
2. Model checkpoint downloaded to $JOB_DIR/model.pt
3. Images extracted FLAT into $JOB_DIR/images/ (all .png/.jpg files directly)
4. Script called as: python script.py --model-path $JOB_DIR/model.pt --images-dir $JOB_DIR/images --output-dir $JOB_DIR/output --job-id XXX
5. Optional: --masks-dir $JOB_DIR/masks (if user provides ground truth for metrics)
6. Must save: output/predictions/*.png, output/metrics.json
"""


# ---------------------------------------------------------------------------
# Generate Inference Code
# ---------------------------------------------------------------------------


class GenInferenceRequest(BaseModel):
    job_id: str = ""
    model_name: str


class GenInferenceResponse(BaseModel):
    message: str
    script_path: str


@router.post("/generate-inference", response_model=GenInferenceResponse)
async def generate_inference_code(body: GenInferenceRequest, user_id: UUID = Depends(require_auth)):
    """Generate inference script based on the training code that succeeded."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Not configured")

    from .db import fetch_one as _fetch_one

    um = await _fetch_one("SELECT * FROM user_models WHERE model_name = $1 AND user_id = $2", body.model_name, user_id)
    if not um:
        raise HTTPException(status_code=404, detail="Model not found")

    train_gcs_path = um["inference_script"]
    bucket = _get_bucket()
    blob = bucket.blob(train_gcs_path)
    if not blob.exists():
        raise HTTPException(status_code=404, detail="Training script not found")
    training_code = blob.download_as_text()

    category = um["category"]
    template_key = "edge_inference" if category == "edge_mask" else "object_inference"
    try:
        template_code = _load_template(template_key)
    except Exception:
        template_code = ""

    prompt = f"""Generate a standalone inference script for this trained model.

TRAINING CODE (shows model architecture):
{training_code[:6000]}

REFERENCE INFERENCE SCRIPT (follow this format):
{template_code[:4000]}

{VM_INFERENCE_CONTEXT}

REQUIREMENTS:
1. Use the SAME model architecture from the training code
2. Follow the SAME CLI interface: --model-path, --images-dir, --output-dir, --job-id, --masks-dir (optional)
3. Load weights from checkpoint: ckpt = torch.load(model_path); model.load_state_dict(ckpt["model"])
4. If --masks-dir provided, compute metrics (edge: dice, boundary_f1, boundary_precision, boundary_recall / object: pixel_accuracy, mean_iou, f1, precision, recall)
5. Save prediction overlay images to output/predictions/
6. Save metrics.json (only if masks provided)
7. Single self-contained file, all imports at top

OUTPUT: ONLY the raw Python code. No markdown."""

    inference_code = await _call_gemini(prompt)
    inference_code = _strip_markdown(inference_code)

    if len(inference_code) < 500:
        raise HTTPException(status_code=502, detail="Failed to generate inference code")

    infer_gcs_path = train_gcs_path.replace("/train.py", "/inference.py")
    bucket.blob(infer_gcs_path).upload_from_string(inference_code, content_type="text/x-python")

    logger.info("Inference script generated: %s", infer_gcs_path)

    return GenInferenceResponse(
        message="Inference script generated.",
        script_path=f"gs://{settings.GCS_BUCKET_NAME}/{infer_gcs_path}",
    )


# ---------------------------------------------------------------------------
# Debug Inference Code
# ---------------------------------------------------------------------------


class DebugInferenceRequest(BaseModel):
    job_id: str
    model_name: str
    user_message: str = ""


class DebugInferenceResponse(BaseModel):
    message: str


@router.post("/debug-inference", response_model=DebugInferenceResponse)
async def debug_inference_code(body: DebugInferenceRequest, user_id: UUID = Depends(require_auth)):
    """Read failed inference job error + current script, ask Gemini to fix, re-upload, re-trigger."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Not configured")

    from .db import fetch_one as _fetch_one

    job = await _fetch_one("SELECT * FROM jobs WHERE id = $1 AND owner_id = $2", body.job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "error":
        raise HTTPException(status_code=400, detail="Job is not in error state")

    error_msg = job["error_message"] or "Unknown error"

    um = await _fetch_one("SELECT * FROM user_models WHERE model_name = $1 AND user_id = $2", body.model_name, user_id)
    if not um:
        raise HTTPException(status_code=404, detail="Model not found")

    gcs_path = um["inference_script"].replace("/train.py", "/inference.py")

    bucket = _get_bucket()
    blob = bucket.blob(gcs_path)
    if not blob.exists():
        raise HTTPException(status_code=404, detail=f"Script not found on GCS: {gcs_path}")

    current_code = blob.download_as_text()

    user_hint = f"\n\nUSER HINT: {body.user_message}" if body.user_message else ""

    debug_prompt = f"""Fix this Python INFERENCE script that failed.

CONTEXT: {VM_INFERENCE_CONTEXT}

ERROR:
{error_msg[-1500:]}

FULL SCRIPT:
{current_code[:12000]}

FIX RULES:
1. CLI args MUST be: --model-path, --images-dir, --output-dir, --job-id (and optional --masks-dir)
2. Load model from checkpoint: ckpt = torch.load(model_path, map_location=device); model.load_state_dict(ckpt["model"])
3. MUST save prediction overlay images in output_dir/predictions/
4. MUST save output_dir/metrics.json (with predictions list at minimum)
5. os.makedirs(output_dir + "/predictions", exist_ok=True) at start
6. Do NOT rename CLI arguments (use dashes: --model-path not --model_path)
7. Common bugs:
   - list index out of range: check model output dimensions, ensure predictions dir exists
   - state_dict key mismatch: try loading with strict=False
   - Device issues: map_location=device when loading
8. Return the COMPLETE fixed script{user_hint}

OUTPUT: ONLY raw Python code. No markdown."""

    fixed_code = await _call_gemini(debug_prompt)
    fixed_code = _strip_markdown(fixed_code)

    if len(fixed_code) < 500:
        raise HTTPException(status_code=502, detail="Debug agent returned invalid code")

    blob.upload_from_string(fixed_code, content_type="text/x-python")
    logger.info("Debug: fixed inference script uploaded to %s", gcs_path)

    await execute(
        "UPDATE jobs SET status = 'running', error_message = NULL, updated_at = NOW() WHERE id = $1",
        body.job_id,
    )

    from .inference_agent import run_agent_inference
    asyncio.get_event_loop().create_task(
        run_agent_inference(str(job["id"]), job["model_id"], job["name"], str(user_id))
    )
    return DebugInferenceResponse(message="Inference code fixed. Inference restarted.")
