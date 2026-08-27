"""Research agent — uses Gemini API with grounded search to suggest architectures."""

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
    """Run research agent: LLM + grounded search to suggest architecture."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Research agent not configured (missing GEMINI_API_KEY)")

    arch_context = _load_architecture()

    system_prompt = f"""You are an ML architecture advisor. Given the user's segmentation task, recommend the BEST architecture.

Available platform models:
{arch_context}

Generate a SHORT (2-3 pages max) focused report:

1. **Task Analysis** (3-4 sentences)
2. **Recommended Architecture** - State explicitly: encoder name, decoder name, input size, loss function
3. **Why This Architecture** - 3-4 bullet points
4. **Training Config** - lr, epochs, batch_size, optimizer, augmentations
5. **Alternative Options** - 2-3 other architectures briefly

IMPORTANT:
- Be SPECIFIC: name exact encoder (e.g. resnet50, efficientnet-b4, convnext_base) and decoder (e.g. UnetPlusPlus, DeepLabV3Plus, FPN)
- State the smp (segmentation_models_pytorch) compatible names
- Keep it concise - this feeds into a coding agent
- No LaTeX, no ASCII art, plain markdown only
- End with a one-line summary: "ARCHITECTURE: [encoder] + [decoder] for [task type]"
"""
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


@router.get("/report/{job_name}")
async def get_report(job_name: str, user_id: UUID = Depends(require_auth)):
    """Get signed URL for the research report of an agent job."""
    from .gcs import mint_signed_get_url, _get_bucket
    report_path = f"agent-scripts/{user_id}/{job_name}/report.md"
    bucket = _get_bucket()
    blob = bucket.blob(report_path)
    if not blob.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    url = mint_signed_get_url(report_path)
    return {"url": url}
