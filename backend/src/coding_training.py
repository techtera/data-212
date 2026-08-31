"""Coding agent — training script generation and debugging."""

import asyncio
import logging
import re
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import require_auth
from .config import settings
from .db import execute, fetch_all
from .gcs import _get_bucket
from .agent_template import AGENT_TRAIN_TEMPLATE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coding", tags=["coding-train"])

TEMPLATE_PATHS = {
    "edge_train": "finetune/code/unetpp_finetune.py",
    "object_train": "finetune/code/yolo_finetune.py",
    "edge_inference": "usr-inference-code/unetpp_inference.py",
    "object_inference": "usr-inference-code/yolo_inference.py",
}


def _load_template(key: str) -> str:
    """Load template code from GCS."""
    bucket = _get_bucket()
    blob = bucket.blob(TEMPLATE_PATHS[key])
    if not blob.exists():
        raise HTTPException(status_code=500, detail=f"Template not found on GCS: {TEMPLATE_PATHS[key]}")
    return blob.download_as_text()


VM_TRAINING_CONTEXT = """
The training script runs on a GPU VM via this bash wrapper:
1. Script downloaded to $JOB_DIR/train.py
2. Images extracted FLAT into $JOB_DIR/images/ (all .png/.jpg files directly, no subfolders)
3. Masks extracted FLAT into $JOB_DIR/masks/ (all mask files directly, no subfolders)
4. Script called as: python train.py --model-path "" --images-dir $JOB_DIR/images --masks-dir $JOB_DIR/masks --output-dir $JOB_DIR/output --job-id XXX --split 0.9
5. Must save: output/best.pt, output/metrics.json, output/predictions/*.png

Mask naming:
- Edge masks: image "abc.png" -> mask "abc_mask.png"
- Object masks: image "abc.png" -> mask "abc.txt" (YOLO polygon format)
"""


async def _call_gemini(prompt: str, max_tokens: int = 16384, temperature: float = 0.1) -> str:
    """Call Gemini API and return text response."""
    async with httpx.AsyncClient(timeout=180) as client:
        response = None
        for attempt in range(3):
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={settings.GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
                },
            )
            if response.status_code == 429:
                await asyncio.sleep(5)
                continue
            break

    if response.status_code != 200:
        logger.error("Gemini error: %d %s", response.status_code, response.text[:200])
        raise HTTPException(status_code=502, detail="AI agent failed to respond")

    text = ""
    data = response.json()
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "text" in part:
                text += part["text"]

    return text.strip()


def _strip_markdown(code: str) -> str:
    """Remove markdown fences from code."""
    code = code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1] if "\n" in code else code[3:]
    if code.endswith("```"):
        code = code.rsplit("```", 1)[0]
    if code.startswith("python"):
        code = code[6:].lstrip("\n")
    return code.strip()


# ---------------------------------------------------------------------------
# Auto-debug (called from polling loop, no HTTP deps)
# ---------------------------------------------------------------------------


async def auto_debug_train(model_name: str, user_id: str, error_msg: str) -> bool:
    """Auto-debug training code. Called from polling loop on error. Returns True if fix uploaded."""
    if not settings.GEMINI_API_KEY:
        return False
    try:
        from .db import fetch_one as _fetch_one
        um = await _fetch_one(
            "SELECT * FROM user_models WHERE model_name = $1 AND user_id = $2",
            model_name, UUID(user_id),
        )
        if not um:
            return False
        gcs_path = um["inference_script"]
        bucket = _get_bucket()
        blob = bucket.blob(gcs_path)
        if not blob.exists():
            return False
        current_code = blob.download_as_text()

        debug_prompt = f"""Fix this Python TRAINING script that failed.

CONTEXT: {VM_TRAINING_CONTEXT}

ERROR:
{error_msg[-1500:]}

FULL SCRIPT:
{current_code[:12000]}

FIX RULES:
1. MUST save output_dir/best.pt using: torch.save({{"model": model.state_dict(), "epoch": N}}, path)
2. MUST save output_dir/metrics.json with: mean_iou, dice_score, pixel_accuracy, epochs_trained, train_metrics, val_metrics, loss_type, epoch_history, predictions
3. MUST save prediction overlay images in output_dir/predictions/
4. CLI args MUST be: --model-path, --images-dir, --masks-dir, --output-dir, --job-id, --split, --epochs, --lr
5. Common bugs:
   - "No pairs found": match by stem_mask.png (edge) or stem.txt (object)
   - Tensor type: use .float() on masks before loss
   - best.pt not found: ensure torch.save runs before function returns
   - os.makedirs(output_dir + "/predictions", exist_ok=True) at start
6. Do NOT rename CLI arguments (use dashes: --model-path not --model_path)
7. Return the COMPLETE fixed script

OUTPUT: ONLY raw Python code. No markdown."""

        fixed_code = await _call_gemini(debug_prompt)
        fixed_code = _strip_markdown(fixed_code)
        if len(fixed_code) < 500:
            return False
        blob.upload_from_string(fixed_code, content_type="text/x-python")
        logger.info("Auto-debug: fixed training script uploaded to %s", gcs_path)
        return True
    except Exception as e:
        logger.warning("Auto-debug train failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Generate Training Code
# ---------------------------------------------------------------------------


class GenTrainRequest(BaseModel):
    report: str = Field(min_length=50)
    job_name: str = Field(min_length=1, max_length=128)
    mask_type: str = "edge"


class GenTrainResponse(BaseModel):
    model_name: str
    script_path: str
    message: str


@router.post("/generate-train", response_model=GenTrainResponse)
async def generate_training_code(body: GenTrainRequest, user_id: UUID = Depends(require_auth)):
    """Generate training script: get model line from Gemini, inject into working template."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Not configured")

    model_prompt = f"""Based on this research report, give me the SINGLE Python line that creates the segmentation model using segmentation_models_pytorch (smp).

RESEARCH REPORT:
{body.report[:2000]}

RULES:
- Use segmentation_models_pytorch (smp)
- Available decoders: Unet, UnetPlusPlus, DeepLabV3Plus, FPN, PSPNet, MAnet, Linknet, PAN
- Available encoders: resnet50, resnet101, efficientnet-b3, efficientnet-b4, efficientnet-b5, mit_b2, mit_b3, mit_b5, convnext_base, convnext_large
- Output: classes=1 (binary), in_channels=3
- Use encoder_weights="imagenet"
- For edge masks include decoder_attention_type="scse" if UnetPlusPlus
- Do NOT include activation= parameter (model MUST output raw logits, loss function handles sigmoid)

OUTPUT EXACTLY ONE LINE like:
smp.DeepLabV3Plus(encoder_name="resnet50", encoder_weights="imagenet", in_channels=3, classes=1)

JUST the smp.XXX(...) call. Nothing else. No activation parameter."""

    model_line = await _call_gemini(model_prompt, max_tokens=256)
    model_line = _strip_markdown(model_line).split("\n")[0].strip()
    if not model_line.startswith("smp."):
        model_line = 'smp.UnetPlusPlus(encoder_name="resnet50", encoder_weights="imagenet", in_channels=3, classes=1)'

    # Sanitize: strip activation= parameter to ensure raw logit output
    model_line = re.sub(r',\s*activation\s*=\s*["\'][^"\']*["\']', '', model_line)

    logger.info("Coding agent model line: %s", model_line)

    # Use embedded template — hardcoded metrics, predictions, JSON output format
    code = AGENT_TRAIN_TEMPLATE
    code = re.sub(r'smp\.UnetPlusPlus\([^)]+\)', model_line, code, count=1)

    gcs_path = f"agent-scripts/{user_id}/{body.job_name}/train.py"
    bucket = _get_bucket()
    bucket.blob(gcs_path).upload_from_string(code, content_type="text/x-python")

    bucket.blob(f"agent-scripts/{user_id}/{body.job_name}/report.md").upload_from_string(
        body.report, content_type="text/markdown"
    )

    logger.info("Training script uploaded: %s", gcs_path)

    category = "edge_mask" if body.mask_type == "edge" else "object_mask"
    existing = await fetch_all(
        "SELECT version FROM user_models WHERE user_id = $1 AND base_model = $2 ORDER BY version DESC LIMIT 1",
        user_id, "agent-generated",
    )
    version = (existing[0]["version"] + 1) if existing else 1
    model_name = f"{body.job_name}_agent_v_{version}"

    await execute(
        """INSERT INTO user_models (user_id, model_name, category, base_model, checkpoint_path, inference_script, version)
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        user_id, model_name, category, "agent-generated", "", gcs_path, version,
    )

    return GenTrainResponse(
        model_name=model_name,
        script_path=f"gs://{settings.GCS_BUCKET_NAME}/{gcs_path}",
        message=f"Training script generated as '{model_name}'.",
    )


# ---------------------------------------------------------------------------
# Debug Training Code
# ---------------------------------------------------------------------------


class DebugTrainRequest(BaseModel):
    job_id: str
    model_name: str
    user_message: str = ""


class DebugTrainResponse(BaseModel):
    message: str


@router.post("/debug", response_model=DebugTrainResponse)
async def debug_training_code(body: DebugTrainRequest, user_id: UUID = Depends(require_auth)):
    """Read failed training job error + current script, ask Gemini to fix, re-upload, re-trigger."""
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

    gcs_path = um["inference_script"]

    bucket = _get_bucket()
    blob = bucket.blob(gcs_path)
    if not blob.exists():
        raise HTTPException(status_code=404, detail=f"Script not found on GCS: {gcs_path}")

    current_code = blob.download_as_text()

    user_hint = f"\n\nUSER HINT: {body.user_message}" if body.user_message else ""

    debug_prompt = f"""Fix this Python TRAINING script that failed.

CONTEXT: {VM_TRAINING_CONTEXT}

ERROR:
{error_msg[-1500:]}

FULL SCRIPT:
{current_code[:12000]}

FIX RULES:
1. MUST save output_dir/best.pt using: torch.save({{"model": model.state_dict(), "epoch": N}}, path)
2. MUST save output_dir/metrics.json with: mean_iou, dice_score, pixel_accuracy, epochs_trained, train_metrics, val_metrics, loss_type, epoch_history, predictions
3. MUST save prediction overlay images in output_dir/predictions/
4. CLI args MUST be: --model-path, --images-dir, --masks-dir, --output-dir, --job-id, --split
5. Common bugs:
   - "No pairs found": match by stem_mask.png (edge) or stem.txt (object)
   - Tensor type: use .float() on masks before loss
   - best.pt not found: ensure torch.save runs before function returns
   - os.makedirs(output_dir + "/predictions", exist_ok=True) at start
6. Do NOT rename CLI arguments (use dashes: --model-path not --model_path)
7. Return the COMPLETE fixed script{user_hint}

OUTPUT: ONLY raw Python code. No markdown."""

    fixed_code = await _call_gemini(debug_prompt)
    fixed_code = _strip_markdown(fixed_code)

    if len(fixed_code) < 500:
        raise HTTPException(status_code=502, detail="Debug agent returned invalid code")

    blob.upload_from_string(fixed_code, content_type="text/x-python")
    logger.info("Debug: fixed training script uploaded to %s", gcs_path)

    await execute(
        "UPDATE jobs SET status = 'running', error_message = NULL, updated_at = NOW() WHERE id = $1",
        body.job_id,
    )

    from .training_agent import run_agent_train
    asyncio.get_event_loop().create_task(
        run_agent_train(str(job["id"]), job["model_id"], job["name"], str(user_id))
    )
    return DebugTrainResponse(message="Training code fixed. Training restarted.")
