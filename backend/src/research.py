"""Research agent — uses Gemini API with grounded search to suggest best model and generate detailed reports."""

import asyncio
import json
import logging
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import require_auth
from .config import settings
from .db import execute, fetch_all
from .gcs import _get_bucket
from .models import _load_models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])

ARCH_FILE = Path(__file__).resolve().parent.parent / "architecture.json"


def _load_architecture() -> str:
    with open(ARCH_FILE, "r") as f:
        arch = json.load(f)
    return json.dumps(arch, indent=2)


class ResearchRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=2000)


class ResearchResponse(BaseModel):
    report: str


@router.post("", response_model=ResearchResponse)
async def run_research(body: ResearchRequest, user_id: UUID = Depends(require_auth)):
    """Run research agent to suggest best model and generate detailed architecture report."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Research agent not configured (missing GEMINI_API_KEY)")

    arch_context = _load_architecture()

    if not settings.RESEARCH_SYSTEM_PROMPT:
        raise HTTPException(status_code=503, detail="Research agent not configured (missing RESEARCH_SYSTEM_PROMPT)")

    raw_prompt = settings.RESEARCH_SYSTEM_PROMPT.replace("\\n", "\n")
    system_prompt = raw_prompt.replace("{arch_context}", arch_context)

    user_prompt = f"My task: {body.prompt}"

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = None
            for attempt in range(3):
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={settings.GEMINI_API_KEY}",
                    json={
                        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 16384},
                        "tools": [{"google_search": {}}],
                    },
                )
                if response.status_code == 429:
                    await asyncio.sleep(5)
                    continue
                break

        if response.status_code != 200:
            logger.error("Gemini API error: %d %s", response.status_code, response.text[:200])
            raise HTTPException(status_code=502, detail="Research agent failed to respond")

        data = response.json()
        text = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    text += part["text"]

        if not text.strip():
            raise HTTPException(status_code=502, detail="Research agent returned empty response")

        return ResearchResponse(report=text.strip())

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Research agent timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Research agent error")
        raise HTTPException(status_code=500, detail=f"Research agent error: {str(e)[:200]}")


# ---------------------------------------------------------------------------
# Code Generation Endpoint
# ---------------------------------------------------------------------------

CODE_GEN_PROMPT_EDGE = None
CODE_GEN_PROMPT_OBJECT = None

EDGE_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "model" / "code" / "finetune_code_unetpp_finetune.py"
OBJECT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "model" / "code" / "finetune_code_yolo_finetune.py"


def _get_code_gen_prompt(mask_type: str, report: str) -> str:
    """Ask Gemini for ONLY the smp model line — we inject it into our template."""
    return f"""Based on this research report, give me the SINGLE Python line that creates the segmentation model using segmentation_models_pytorch (smp).

RESEARCH REPORT:
{report}

RULES:
- Use segmentation_models_pytorch (smp)
- Available decoders: Unet, UnetPlusPlus, DeepLabV3Plus, FPN, PSPNet, MAnet, Linknet, PAN
- Available encoders: resnet50, resnet101, efficientnet-b3, efficientnet-b4, efficientnet-b5, mit_b2, mit_b3, mit_b5, convnext_base, convnext_large, tu-convnext_base
- Output: classes=1 (binary), in_channels=3
- Use encoder_weights="imagenet"
- For edge masks use decoder_attention_type="scse" if UnetPlusPlus

OUTPUT EXACTLY ONE LINE like:
smp.DeepLabV3Plus(encoder_name="resnet50", encoder_weights="imagenet", in_channels=3, classes=1)

No explanation, no imports, no markdown. JUST the smp.XXX(...) call."""


class GenerateCodeRequest(BaseModel):
    report: str = Field(min_length=50)
    job_name: str = Field(min_length=1, max_length=128)
    mask_type: str = "edge"


class GenerateCodeResponse(BaseModel):
    model_name: str
    script_path: str
    message: str


@router.post("/generate-code", response_model=GenerateCodeResponse)
async def generate_training_code(body: GenerateCodeRequest, user_id: UUID = Depends(require_auth)):
    """Generate a training script by injecting AI-recommended model into our working template."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Not configured (missing GEMINI_API_KEY)")

    prompt = _get_code_gen_prompt(body.mask_type, body.report)

    try:
        # Ask Gemini for just the model line
        async with httpx.AsyncClient(timeout=60) as client:
            response = None
            for attempt in range(3):
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={settings.GEMINI_API_KEY}",
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 256},
                    },
                )
                if response.status_code == 429:
                    await asyncio.sleep(5)
                    continue
                break

        if response.status_code != 200:
            logger.error("Gemini code gen error: %d %s", response.status_code, response.text[:200])
            raise HTTPException(status_code=502, detail="Code generation failed")

        data = response.json()
        model_line = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    model_line += part["text"]

        model_line = model_line.strip().replace("```python", "").replace("```", "").strip()
        if not model_line.startswith("smp."):
            model_line = "smp.UnetPlusPlus(encoder_name=\"resnet50\", encoder_weights=\"imagenet\", in_channels=3, classes=1)"

        logger.info("Agent model line: %s", model_line)

        # Always use edge (UNet++) template — works for both edge and object with smp
        if not EDGE_TEMPLATE_PATH.exists():
            raise HTTPException(status_code=500, detail="Training template not found")

        code = EDGE_TEMPLATE_PATH.read_text()

        # Replace the smp model line using regex (handles any whitespace)
        import re
        code = re.sub(
            r'smp\.UnetPlusPlus\([^)]+\)',
            model_line,
            code,
            count=1,
        )
        # Ensure encoder_weights is imagenet for fresh training
        code = code.replace('encoder_weights=None', 'encoder_weights="imagenet"')

        # Upload to GCS
        gcs_path = f"agent-scripts/{user_id}/{body.job_name}/train.py"
        bucket = _get_bucket()
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(code, content_type="text/x-python")
        logger.info("Agent script uploaded to gs://%s/%s", settings.GCS_BUCKET_NAME, gcs_path)

        # Also save the research report
        report_path = f"agent-scripts/{user_id}/{body.job_name}/report.md"
        bucket.blob(report_path).upload_from_string(body.report, content_type="text/markdown")

        # Determine category from report content
        category = "object_mask"
        edge_keywords = ["edge", "boundary", "contour", "skeleton", "seam"]
        if any(kw in body.report.lower()[:500] for kw in edge_keywords):
            category = "edge_mask"

        # Get version
        existing = await fetch_all(
            "SELECT version FROM user_models WHERE user_id = $1 AND base_model = $2 ORDER BY version DESC LIMIT 1",
            user_id, "agent-generated",
        )
        version = (existing[0]["version"] + 1) if existing else 1
        model_name = f"{body.job_name}_agent_v_{version}"

        # Register model
        await execute(
            """INSERT INTO user_models (user_id, model_name, category, base_model, checkpoint_path, inference_script, version)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            user_id, model_name, category, "agent-generated", "", gcs_path, version,
        )

        return GenerateCodeResponse(
            model_name=model_name,
            script_path=f"gs://{settings.GCS_BUCKET_NAME}/{gcs_path}",
            message=f"Training script generated and registered as '{model_name}'. Select it from the model list to start fine-tuning.",
        )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Code generation timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Code generation error")
        raise HTTPException(status_code=500, detail=f"Code generation error: {str(e)[:200]}")


# ---------------------------------------------------------------------------
# Debug Code Endpoint
# ---------------------------------------------------------------------------

@router.get("/report/{job_name}")
async def get_report(job_name: str, user_id: UUID = Depends(require_auth)):
    """Get signed URL for the research report of an agent job."""
    from .gcs import mint_signed_get_url
    report_path = f"agent-scripts/{user_id}/{job_name}/report.md"
    bucket = _get_bucket()
    blob = bucket.blob(report_path)
    if not blob.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    url = mint_signed_get_url(report_path)
    return {"url": url}


class DebugCodeRequest(BaseModel):
    job_id: str
    model_name: str
    user_message: str = ""


class DebugCodeResponse(BaseModel):
    message: str


@router.post("/debug-code", response_model=DebugCodeResponse)
async def debug_training_code(body: DebugCodeRequest, user_id: UUID = Depends(require_auth)):
    """Read failed job error + current script, ask Gemini to fix, re-upload, re-trigger training."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Not configured")

    from .db import fetch_one as _fetch_one

    # Get job error message
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

    gcs_path = um["inference_script"]
    bucket = _get_bucket()
    blob = bucket.blob(gcs_path)
    if not blob.exists():
        raise HTTPException(status_code=404, detail="Training script not found on GCS")

    current_code = blob.download_as_text()


    # Ask Gemini to fix the code
    user_hint = f"\n\nUSER HINT: {body.user_message}" if body.user_message else ""

    debug_prompt = f"""Fix this Python training script that failed.

CONTEXT: The script is called by a bash wrapper on a GPU VM like this:
  python train.py --model-path "" --images-dir "$JOB_DIR/images" --masks-dir "$JOB_DIR/masks" --output-dir "$JOB_DIR/output" --job-id XXX --split 0.9

The bash wrapper extracts images.zip into $JOB_DIR/images/ (flat, all .png/.jpg files directly in this folder)
and masks.zip into $JOB_DIR/masks/ (flat, all mask files directly in this folder).

Mask naming convention:
- Edge masks: if image is "abc.png", mask is "abc_mask.png" in masks folder
- Object masks: if image is "abc.png", mask is "abc.txt" (YOLO polygon format) in masks folder

Here's the error:

ERROR:
{error_msg[-1500:]}

FULL SCRIPT:
{current_code[:12000]}

FIX RULES:
1. The script MUST save output_dir/best.pt using: torch.save({{"model": model.state_dict(), "epoch": N}}, path)
2. The script MUST save output_dir/metrics.json with train_metrics, val_metrics, epoch_history
3. The script MUST save prediction images in output_dir/predictions/
4. CLI args MUST be: --model-path, --images-dir, --masks-dir, --output-dir, --job-id, --split, --epochs, --lr
5. Common bugs to fix:
   - "No pairs found": masks are either stem_mask.png (edge) or stem.txt (YOLO object). Match by: for _mask.png try image stem + "_mask.png", for .txt try image stem + ".txt"
   - Tensor type mismatch: always use .float() on masks before loss
   - FileNotFoundError on best.pt: ensure torch.save is called INSIDE the training function before it returns
   - Missing output directory: use os.makedirs(output_dir + "/predictions", exist_ok=True) at start
   - Dimension errors: ensure model output and mask have same spatial dimensions (use F.interpolate if needed)
6. Do NOT rename CLI arguments (use dashes not underscores: --model-path not --model_path)
7. Return the COMPLETE fixed script

OUTPUT: ONLY the raw Python code. No markdown fences. No explanation.{user_hint}"""

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = None
            for attempt in range(3):
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={settings.GEMINI_API_KEY}",
                    json={
                        "contents": [{"parts": [{"text": debug_prompt}]}],
                        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 16384},
                    },
                )
                if response.status_code == 429:
                    await asyncio.sleep(5)
                    continue
                break

        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Debug agent failed")

        data = response.json()
        fixed_code = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    fixed_code += part["text"]

        fixed_code = fixed_code.strip()
        if fixed_code.startswith("```"):
            fixed_code = fixed_code.split("\n", 1)[1]
        if fixed_code.endswith("```"):
            fixed_code = fixed_code.rsplit("```", 1)[0]
        if fixed_code.startswith("python"):
            fixed_code = fixed_code[6:].lstrip("\n")
        fixed_code = fixed_code.strip()

        if not fixed_code or len(fixed_code) < 500:
            raise HTTPException(status_code=502, detail="Debug agent returned invalid code")

        # Upload fixed code
        blob.upload_from_string(fixed_code, content_type="text/x-python")
        logger.info("Debug: fixed script uploaded to %s", gcs_path)

        # Reset job status and re-trigger
        await execute(
            "UPDATE jobs SET status = 'running', error_message = NULL, updated_at = NOW() WHERE id = $1",
            body.job_id,
        )

        # Launch agent training (separate from normal finetune)
        from .training import run_agent_train
        import asyncio as aio
        aio.get_event_loop().create_task(
            run_agent_train(str(job["id"]), job["model_id"], job["name"], str(user_id))
        )

        return DebugCodeResponse(message="Code fixed. Training restarted.")

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Debug agent timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Debug code error")
        raise HTTPException(status_code=500, detail=f"Debug error: {str(e)[:200]}")
