"""TERAFAC Research Agent — Cloud Run container.

Stateless FastAPI service that:
1. Accepts POST /run with { job_id, hop_token, registry_context }
2. Verifies the hop token (step="research", audience="terafac-worker")
3. Calls Gemini API with grounded Search for analysis
4. Returns { findings, risk_score, confidence, risk_tier }

Security rules:
- This container has NO GCS bucket mount and NO direct write access anywhere.
- It can only return findings through the broker (the caller).
- NEVER log raw hop tokens — only job_id and metadata.
- No local model weights — uses Google-hosted Gemini API only.
"""

from __future__ import annotations

import logging
import os
import time

import jwt
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

# ── Config from environment ───────────────────────────────────────────────────
JWT_HOP_SECRET = os.environ.get("JWT_HOP_SECRET", "")
JWT_HOP_ISSUER = os.environ.get("JWT_HOP_ISSUER", "terafac-api")
JWT_HOP_AUDIENCE = os.environ.get("JWT_HOP_AUDIENCE", "terafac-worker")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
PORT = int(os.environ.get("PORT", "8001"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("research-agent")

app = FastAPI(title="TERAFAC Research Agent", version="0.1.0")


# ── Request/Response schemas ──────────────────────────────────────────────────


class ResearchRequest(BaseModel):
    job_id: str
    hop_token: str
    registry_context: dict = {}  # type: ignore[type-arg]


class ResearchResponse(BaseModel):
    findings: str
    risk_score: float
    confidence: float
    risk_tier: str  # "low" | "medium" | "high"


# ── Hop token verification (duplicated from main backend for isolation) ───────


def verify_hop_token(token: str) -> dict:
    """Verify the hop token is valid, unexpired, and scoped to step=research.

    Raises HTTPException(401) on any failure.
    NEVER logs the raw token.
    """
    if not JWT_HOP_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_HOP_SECRET not configured on research agent",
        )

    try:
        payload = jwt.decode(
            token,
            JWT_HOP_SECRET,
            algorithms=["HS256"],
            issuer=JWT_HOP_ISSUER,
            audience=JWT_HOP_AUDIENCE,
        )
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hop token expired",
        ) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid hop token",
        ) from err

    if payload.get("step") != "research":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hop token step mismatch — expected 'research'",
        )

    # Log verification metadata only — NEVER the raw token
    logger.info(
        "hop_token_verified job_id=%s step=%s",
        payload.get("sub"),
        payload.get("step"),
    )
    return payload


# ── Gemini API call (or stub) ─────────────────────────────────────────────────


async def call_gemini(prompt: str, context: dict) -> dict:  # type: ignore[type-arg]
    """Call Gemini API for research analysis.

    When GEMINI_API_KEY is not set, returns canned findings (dev mode).
    In production, calls the real Gemini API with grounded Search.
    """
    if not GEMINI_API_KEY:
        # Dev stub — return canned findings
        logger.info("Gemini stub mode (no API key) — returning canned findings")
        return {
            "findings": (
                f"Research agent analyzed the request: '{prompt[:100]}'. "
                "The proposed configuration uses standard segmentation architecture. "
                "Dataset appears to be within normal parameters. "
                "No adversarial patterns or safety concerns detected. "
                "Model architecture is well-established (U-Net variant). "
                "Confidence: high. Recommendation: proceed with training."
            ),
            "risk_score": 0.25,
            "confidence": 0.88,
        }

    # Production: call Gemini API
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-3-flash-preview")

        # Extract available architectures from context
        available_models = context.get("available_architectures", [])
        models_description = ""
        if available_models:
            models_description = "\n\nAVAILABLE MODEL ARCHITECTURES IN REGISTRY:\n"
            for m in available_models:
                import json as _json
                models_description += f"\n--- {m.get('model_name', 'Unknown')} ---\n"
                arch = m.get("architecture", {})
                models_description += f"Architecture:\n{_json.dumps(arch, indent=2)}\n"

        dataset_desc = context.get("dataset_description", "")
        dataset_path = context.get("dataset_object_path", "")

        system_prompt = """You are a senior ML research agent for the TERAFAC auto-training pipeline.
Your job is to analyze a training request and recommend the best model architecture.

You must:
1. Analyze the user's training prompt and dataset description
2. Review the available model architectures in the registry
3. Either SELECT the best existing architecture OR PROPOSE modifications/a new architecture
4. Provide a risk assessment for the training job

Your response MUST be valid JSON with exactly these fields:
{
  "findings": "A detailed 3-5 sentence analysis explaining your recommendation",
  "risk_score": 0.0 to 1.0 (0=safe, 1=dangerous),
  "confidence": 0.0 to 1.0 (your confidence in this recommendation),
  "recommended_architecture": "The model_id you recommend OR 'custom' if proposing new",
  "architecture_reasoning": "Why this architecture is best for this task",
  "proposed_config": { "any training config overrides you recommend" }
}"""

        user_msg = f"""TRAINING REQUEST:
Prompt: {prompt}
Dataset path: {dataset_path}
Dataset description: {dataset_desc if dataset_desc else 'Aerial/satellite imagery for segmentation (building detection task)'}
{models_description}

Based on the above, analyze this request and recommend the best approach.
Consider: dataset size implications, task complexity, available compute, and model suitability."""

        response = model.generate_content(
            [system_prompt, user_msg],
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )

        import json

        result = json.loads(response.text)
        
        # Build comprehensive findings string
        findings = result.get("findings", "Analysis complete.")
        rec_arch = result.get("recommended_architecture", "")
        arch_reasoning = result.get("architecture_reasoning", "")
        proposed_config = result.get("proposed_config", {})
        
        full_findings = (
            f"{findings}\n\n"
            f"RECOMMENDED ARCHITECTURE: {rec_arch}\n"
            f"REASONING: {arch_reasoning}\n"
        )
        if proposed_config:
            full_findings += f"PROPOSED CONFIG OVERRIDES: {json.dumps(proposed_config, indent=2)}\n"

        return {
            "findings": full_findings,
            "risk_score": float(result.get("risk_score", 0.3)),
            "confidence": float(result.get("confidence", 0.8)),
        }
    except Exception as e:
        logger.warning("Gemini API call failed: %s: %s", type(e).__name__, str(e)[:200])
        return {
            "findings": f"Research agent encountered an error calling Gemini ({type(e).__name__}: {str(e)[:100]}). Manual review recommended.",
            "risk_score": 0.8,
            "confidence": 0.2,
        }


# ── Main endpoint ─────────────────────────────────────────────────────────────


@app.post("/run", response_model=ResearchResponse)
async def run_research(req: ResearchRequest) -> ResearchResponse:
    """Execute research analysis for a job.

    1. Verify hop token (must be scoped to step="research")
    2. Call Gemini with the job context
    3. Score risk tier based on risk_score
    4. Return findings to the broker

    This endpoint has NO side effects — no writes to Firestore, GCS, or anywhere.
    All results flow back through the broker only.
    """
    # Step 1: Verify hop token
    claims = verify_hop_token(req.hop_token)
    logger.info("Research request accepted for job_id=%s", req.job_id)

    # Verify job_id matches token subject
    if claims.get("sub") != req.job_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hop token subject does not match job_id",
        )

    # Step 2: Call Gemini
    prompt = req.registry_context.get("prompt", "")
    gemini_result = await call_gemini(prompt, req.registry_context)

    # Step 3: Score risk tier
    risk_score = gemini_result["risk_score"]
    if risk_score < 0.3:
        risk_tier = "low"
    elif risk_score < 0.7:
        risk_tier = "medium"
    else:
        risk_tier = "high"

    # Step 4: Return findings (no writes, no side effects)
    logger.info(
        "Research complete for job_id=%s risk_tier=%s risk_score=%.2f",
        req.job_id,
        risk_tier,
        risk_score,
    )

    return ResearchResponse(
        findings=gemini_result["findings"],
        risk_score=risk_score,
        confidence=gemini_result["confidence"],
        risk_tier=risk_tier,
    )


@app.get("/health")
async def health():
    """Health check for Cloud Run."""
    return {"status": "ok", "service": "research-agent", "timestamp": int(time.time())}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
