"""Coding agent — generates and debugs training/inference scripts using Gemini LLM."""

import asyncio
import json
import logging
import re
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import require_auth
from .config import settings
from .db import execute, fetch_all
from .gcs import _get_bucket

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coding", tags=["coding"])

# Template paths
EDGE_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "model" / "code" / "finetune_code_unetpp_finetune.py"
OBJECT_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "model" / "code" / "finetune_code_yolo_finetune.py"
EDGE_INFERENCE_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "model" / "code" / "usr_unetpp_inference.py"
OBJECT_INFERENCE_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "model" / "code" / "usr_yolo_inference.py"

# VM context shared with agent
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

VM_INFERENCE_CONTEXT = """
The inference script runs on a GPU VM via this bash wrapper:
1. Script downloaded to $JOB_DIR/script.py
2. Model checkpoint downloaded to $JOB_DIR/model.pt
3. Images extracted FLAT into $JOB_DIR/images/ (all .png/.jpg files directly)
4. Script called as: python script.py --model-path $JOB_DIR/model.pt --images-dir $JOB_DIR/images --output-dir $JOB_DIR/output --job-id XXX
5. Optional: --masks-dir $JOB_DIR/masks (if user provides ground truth for metrics)
6. Must save: output/predictions/*.png, output/metrics.json
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

    # Step 1: Get model architecture line from Gemini
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

OUTPUT EXACTLY ONE LINE like:
smp.DeepLabV3Plus(encoder_name="resnet50", encoder_weights="imagenet", in_channels=3, classes=1)

JUST the smp.XXX(...) call. Nothing else."""

    model_line = await _call_gemini(model_prompt, max_tokens=256)
    model_line = _strip_markdown(model_line).split("\n")[0].strip()
    if not model_line.startswith("smp."):
        model_line = 'smp.UnetPlusPlus(encoder_name="resnet50", encoder_weights="imagenet", in_channels=3, classes=1)'

    logger.info("Coding agent model line: %s", model_line)

    # Step 2: Load template and inject model line
    template_path = EDGE_TEMPLATE if body.mask_type == "edge" else OBJECT_TEMPLATE
    if not template_path.exists():
        raise HTTPException(status_code=500, detail="Training template not found")

    code = template_path.read_text()
    code = re.sub(r'smp\.UnetPlusPlus\([^)]+\)', model_line, code, count=1)
    code = code.replace('encoder_weights=None', 'encoder_weights="imagenet"')

    # Step 3: Upload to GCS
    gcs_path = f"agent-scripts/{user_id}/{body.job_name}/train.py"
    bucket = _get_bucket()
    bucket.blob(gcs_path).upload_from_string(code, content_type="text/x-python")

    # Save report too
    bucket.blob(f"agent-scripts/{user_id}/{body.job_name}/report.md").upload_from_string(
        body.report, content_type="text/markdown"
    )

    logger.info("Training script uploaded: %s", gcs_path)

    # Step 4: Register model
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
# Generate Inference Code (after training succeeds)
# ---------------------------------------------------------------------------

class GenInferenceRequest(BaseModel):
    job_id: str
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

    # Get model info
    um = await _fetch_one("SELECT * FROM user_models WHERE model_name = $1 AND user_id = $2", body.model_name, user_id)
    if not um:
        raise HTTPException(status_code=404, detail="Model not found")

    # Read training code from GCS
    train_gcs_path = um["inference_script"]
    bucket = _get_bucket()
    blob = bucket.blob(train_gcs_path)
    if not blob.exists():
        raise HTTPException(status_code=404, detail="Training script not found")
    training_code = blob.download_as_text()

    # Load inference template
    category = um["category"]
    if category == "edge_mask":
        template_path = EDGE_INFERENCE_TEMPLATE
    else:
        template_path = OBJECT_INFERENCE_TEMPLATE

    template_code = template_path.read_text() if template_path.exists() else ""

    # Ask Gemini to generate inference code
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

    # Upload inference script (at predictable path, don't overwrite training_script column)
    infer_gcs_path = train_gcs_path.replace("/train.py", "/inference.py")
    bucket.blob(infer_gcs_path).upload_from_string(inference_code, content_type="text/x-python")

    logger.info("Inference script generated: %s", infer_gcs_path)

    return GenInferenceResponse(
        message="Inference script generated.",
        script_path=f"gs://{settings.GCS_BUCKET_NAME}/{infer_gcs_path}",
    )


# ---------------------------------------------------------------------------
# Debug Code (fix failed training/inference)
# ---------------------------------------------------------------------------

class DebugRequest(BaseModel):
    job_id: str
    model_name: str
    user_message: str = ""


class DebugResponse(BaseModel):
    message: str


@router.post("/debug", response_model=DebugResponse)
async def debug_code(body: DebugRequest, user_id: UUID = Depends(require_auth)):
    """Read failed job error + current script, ask Gemini to fix, re-upload, re-trigger."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Not configured")

    from .db import fetch_one as _fetch_one

    job = await _fetch_one("SELECT * FROM jobs WHERE id = $1 AND owner_id = $2", body.job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "error":
        raise HTTPException(status_code=400, detail="Job is not in error state")

    error_msg = job["error_message"] or "Unknown error"

    # Get current script from GCS
    um = await _fetch_one("SELECT * FROM user_models WHERE model_name = $1 AND user_id = $2", body.model_name, user_id)
    if not um:
        raise HTTPException(status_code=404, detail="Model not found")

    # Determine which script to fix based on job type
    is_inference = job["job_type"] == "eval"
    if is_inference:
        gcs_path = um["inference_script"].replace("/train.py", "/inference.py")
    else:
        gcs_path = um["inference_script"]

    bucket = _get_bucket()
    blob = bucket.blob(gcs_path)
    if not blob.exists():
        raise HTTPException(status_code=404, detail=f"Script not found on GCS: {gcs_path}")

    current_code = blob.download_as_text()

    user_hint = f"\n\nUSER HINT: {body.user_message}" if body.user_message else ""

    if is_inference:
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
    else:
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

    # Upload fixed code
    blob.upload_from_string(fixed_code, content_type="text/x-python")
    logger.info("Debug: fixed script uploaded to %s", gcs_path)

    # Reset job and re-trigger based on job type
    await execute(
        "UPDATE jobs SET status = 'running', error_message = NULL, updated_at = NOW() WHERE id = $1",
        body.job_id,
    )

    if job["job_type"] == "eval":
        from .inference_agent import run_agent_inference
        asyncio.get_event_loop().create_task(
            run_agent_inference(str(job["id"]), job["model_id"], job["name"], str(user_id))
        )
        return DebugResponse(message="Code fixed. Inference restarted.")
    else:
        from .training_agent import run_agent_train
        asyncio.get_event_loop().create_task(
            run_agent_train(str(job["id"]), job["model_id"], job["name"], str(user_id))
        )
        return DebugResponse(message="Code fixed. Training restarted.")
