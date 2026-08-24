"""Research agent — uses Gemini API with grounded search to suggest best model."""

import json
import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import require_auth
from .config import settings
from .db import execute, fetch_one
from .models import _load_models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])

MODELS_CONTEXT = """
Available models for segmentation tasks:

1. YOLO11L-MASKING-MODEL (Object Mask)
   - Architecture: YOLOv11 Large with instance segmentation head
   - Best for: Detecting and segmenting discrete objects (parts, weld pieces, products)
   - Input: RGB images, outputs colored mask overlays per detected object
   - Strengths: Fast inference, good at multiple objects, handles varying sizes

2. VGGT-SEGFORMER (Object Mask)
   - Architecture: Vision Geometry Grounded Transformer (ViT-Large) + SegFormer decoder
   - Best for: Semantic segmentation of complex scenes, large objects, fine boundaries
   - Input: RGB images, outputs red mask overlay on object regions
   - Strengths: High accuracy on complex geometries, transformer-based global context

3. UNETPLUSPLUS-MODEL (Edge Mask)
   - Architecture: UNet++ with EfficientNet-B3 encoder + SCSE attention
   - Best for: Edge detection, boundary tracing, weld seam detection, contour extraction
   - Input: RGB images, outputs thin green edge skeleton overlay
   - Strengths: Precise edge localization, skeletonization post-processing

4. VGGT-UNETPP (Edge Mask)
   - Architecture: Vision Geometry Grounded Transformer (ViT-Large) + UNet++ decoder + Edge Refinement
   - Best for: High-precision edge detection on complex industrial parts
   - Input: RGB images, outputs green edge overlay
   - Strengths: Transformer backbone captures global context for better edge continuity
"""


class ResearchRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=2000)


class ResearchResponse(BaseModel):
    recommendation: str
    suggested_model: str
    reasoning: str


@router.post("", response_model=ResearchResponse)
async def run_research(body: ResearchRequest, user_id: UUID = Depends(require_auth)):
    """Run research agent to suggest best model for user's task."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Research agent not configured (missing GEMINI_API_KEY)")

    system_prompt = f"""You are a machine learning architecture advisor for an industrial image segmentation platform.

{MODELS_CONTEXT}

The user will describe their task, data, and requirements. Based on this:
1. Recommend the BEST model from the 4 available options above
2. Explain WHY this model is the best fit (2-3 sentences)
3. Mention what results they can expect

IMPORTANT: You MUST respond in this exact JSON format:
{{"suggested_model": "<exact model name from the list>", "reasoning": "<why this model is best>", "recommendation": "<full recommendation with tips>"}}

The model name must be exactly one of: YOLO11L-MASKING-MODEL, VGGT-SEGFORMER, UNETPLUSPLUS-MODEL, VGGT-UNETPP"""

    user_prompt = f"My task: {body.prompt}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
                    "tools": [{"google_search": {}}],
                },
            )

        if response.status_code != 200:
            logger.error("Gemini API error: %d %s", response.status_code, response.text[:200])
            raise HTTPException(status_code=502, detail="Research agent failed to respond")

        data = response.json()
        text = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    text += part["text"]

        try:
            text_clean = text.strip()
            if text_clean.startswith("```"):
                text_clean = text_clean.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text_clean)
        except json.JSONDecodeError:
            result = {
                "suggested_model": "YOLO11L-MASKING-MODEL",
                "reasoning": text[:500],
                "recommendation": text[:1000],
            }

        valid_models = [m["model_name"] for m in _load_models()]
        if result.get("suggested_model") not in valid_models:
            result["suggested_model"] = valid_models[0]

        return ResearchResponse(
            recommendation=result.get("recommendation", result.get("reasoning", "")),
            suggested_model=result["suggested_model"],
            reasoning=result.get("reasoning", ""),
        )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Research agent timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Research agent error")
        raise HTTPException(status_code=500, detail=f"Research agent error: {str(e)[:200]}")
