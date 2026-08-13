"""V4: Research agent service.

Calls the research agent (Cloud Run container or local stub) with a
scoped hop token + registry context. The agent returns findings which
are stored on the job document, advancing the job to awaiting_approval.

Security rules:
- The research agent receives a hop token scoped to step="research".
- The broker verifies the token before dispatching.
- Findings are returned THROUGH the broker — the research agent has
  no direct write access to Firestore or GCS.
- NEVER log raw hop tokens — only metadata is logged.
"""

from __future__ import annotations

import logging

import httpx

from src.config import get_settings
from src.db.crud import get_doc, query_docs, update_doc
from src.schemas.job import JobStatus

logger = logging.getLogger(__name__)

COLLECTION = "jobs"
REGISTRY_COLLECTION = "model_registry"

# ── Research delay for local stub mode (no real Gemini call) ──────────────────
RESEARCH_STUB_DELAY: float = 3.0


class ResearchFindings:
    """Container for research agent output."""

    def __init__(self, findings: str, risk_score: float, confidence: float, risk_tier: str):
        self.findings = findings
        self.risk_score = risk_score
        self.confidence = confidence
        self.risk_tier = risk_tier


def fetch_model_registry() -> list[dict]:
    """Fetch all model architectures from the model_registry collection.

    This is Path C: an internal backend read (no hop token needed, no auth
    boundary crossed). The registry data is passed to the research agent
    as part of the request payload so the agent can propose/choose architectures.

    Returns:
        List of {model_name, architecture} dicts from Firestore.
    """
    try:
        docs = query_docs(REGISTRY_COLLECTION, limit=50)
        models = []
        for doc in docs:
            models.append(
                {
                    "model_name": doc.get("model_name", ""),
                    "architecture": doc.get("architecture", {}),
                }
            )
        logger.info("Registry: fetched %d model architectures", len(models))
        return models
    except Exception:
        logger.warning("Registry: failed to fetch model architectures (proceeding without)")
        return []


async def call_research_agent(
    job_id: str,
    hop_token: str,
    registry_context: dict | None = None,
) -> ResearchFindings:
    """Call the research agent endpoint with the hop token and context.

    In production: HTTP POST to Cloud Run research agent URL.
    In dev/test: if GEMINI_API_KEY is empty, returns canned findings.

    The research agent verifies the hop token on its side, calls Gemini
    with grounded Search, and returns findings + risk score.

    Args:
        job_id:          The job being researched.
        hop_token:       Short-lived JWT scoped to step="research".
        registry_context: Existing registry entry data (optional).

    Returns:
        ResearchFindings with the agent's output.
    """
    settings = get_settings()

    # If no Gemini key configured, use local stub (dev mode)
    if not settings.gemini_api_key:
        return await _stub_research(job_id, registry_context)

    # Production: call the research agent Cloud Run container
    url = settings.research_agent_url
    payload = {
        "job_id": job_id,
        "hop_token": hop_token,
        "registry_context": registry_context or {},
    }

    try:
        async with httpx.AsyncClient(timeout=settings.research_timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return ResearchFindings(
                findings=data.get("findings", ""),
                risk_score=float(data.get("risk_score", 0.5)),
                confidence=float(data.get("confidence", 0.8)),
                risk_tier=data.get("risk_tier", "medium"),
            )
    except Exception:
        # Research agent unreachable — force manual review (fail-safe)
        # NEVER bypass the container — security requires independent hop token verification
        logger.error(
            "Research agent UNREACHABLE for job_id=%s — ensure agent is running on %s",
            job_id,
            url,
        )
        return ResearchFindings(
            findings=(
                "RESEARCH AGENT UNREACHABLE. The research agent container must be running "
                f"at {url} for security verification. Start it with:\n\n"
                "  python cloud_run/research_agent/main.py\n\n"
                "Manual review required until agent is available."
            ),
            risk_score=0.9,
            confidence=0.1,
            risk_tier="high",
        )


async def _inline_gemini_fallback(
    job_id: str, hop_token: str, registry_context: dict | None = None
) -> ResearchFindings:
    """Fallback: call Gemini directly from backend when research agent is unreachable.

    This runs ONLY when the Cloud Run research agent container is not available
    (e.g. local dev without starting the agent separately). In production the
    agent container should always be reachable.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return ResearchFindings(
            findings="Research agent unreachable and no GEMINI_API_KEY configured.",
            risk_score=0.9,
            confidence=0.1,
            risk_tier="high",
        )

    logger.info("Job %s: inline Gemini fallback (agent unreachable)", job_id)

    try:
        import json as _json

        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-3-flash-preview")

        # Build architecture description
        models_desc = ""
        available = (registry_context or {}).get("available_architectures", [])
        if available:
            models_desc = "\n\nAVAILABLE MODEL ARCHITECTURES:\n"
            for m in available:
                models_desc += f"\n--- {m.get('model_name', '?')} ---\n"
                models_desc += f"Architecture:\n{_json.dumps(m.get('architecture', {}), indent=2)}\n"

        prompt = (registry_context or {}).get("prompt", "")

        system_prompt = """You are a senior ML research agent for the TERAFAC auto-training pipeline.
Analyze the training request and recommend the best model architecture.

You must:
1. Analyze the user's training prompt
2. Review available model architectures
3. SELECT the best existing architecture OR PROPOSE modifications
4. Provide risk assessment

Response MUST be valid JSON:
{
  "findings": "3-5 sentence analysis",
  "risk_score": 0.0 to 1.0,
  "confidence": 0.0 to 1.0,
  "recommended_architecture": "model name",
  "architecture_reasoning": "why this is best",
  "proposed_config": {}
}"""

        user_msg = f"TRAINING REQUEST:\nPrompt: {prompt}\n{models_desc}\n\nRecommend the best approach."

        import asyncio

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                [system_prompt, user_msg],
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            ),
        )

        result = _json.loads(response.text)

        findings = result.get("findings", "Analysis complete.")
        rec_arch = result.get("recommended_architecture", "")
        arch_reasoning = result.get("architecture_reasoning", "")
        proposed_config = result.get("proposed_config", {})

        full_findings = f"{findings}\n\nRECOMMENDED ARCHITECTURE: {rec_arch}\nREASONING: {arch_reasoning}\n"
        if proposed_config:
            full_findings += f"PROPOSED CONFIG OVERRIDES: {_json.dumps(proposed_config, indent=2)}\n"

        risk_score = float(result.get("risk_score", 0.3))
        if risk_score < 0.3:
            risk_tier = "low"
        elif risk_score < 0.7:
            risk_tier = "medium"
        else:
            risk_tier = "high"

        return ResearchFindings(
            findings=full_findings,
            risk_score=risk_score,
            confidence=float(result.get("confidence", 0.8)),
            risk_tier=risk_tier,
        )
    except Exception as e:
        logger.warning("Inline Gemini fallback failed: %s: %s", type(e).__name__, str(e)[:100])
        return ResearchFindings(
            findings=f"Research failed ({type(e).__name__}). Manual review required.",
            risk_score=0.9,
            confidence=0.1,
            risk_tier="high",
        )


async def _stub_research(job_id: str, registry_context: dict | None = None) -> ResearchFindings:
    """Local dev stub — returns canned research findings after a short delay.

    Simulates what the Cloud Run research agent would return. Uses asyncio.sleep
    to mimic network latency.
    """
    import asyncio

    logger.info("Research stub: running for job_id=%s (%.1fs delay)", job_id, RESEARCH_STUB_DELAY)
    await asyncio.sleep(RESEARCH_STUB_DELAY)

    # Generate context-aware stub findings
    prompt = ""
    if registry_context:
        prompt = registry_context.get("prompt", "")

    findings = (
        f"Research agent reviewed the dataset and model configuration for job {job_id}. "
        f"Prompt: '{prompt or 'segmentation task'}'. "
        "Analysis: The proposed training configuration uses standard segmentation "
        "architecture with no unusual data sources. Dataset size and complexity are "
        "within normal parameters. No safety concerns or adversarial patterns detected "
        "in the annotation set. Model architecture is well-established (U-Net variant). "
        "Recommendation: Proceed with training under standard monitoring."
    )

    return ResearchFindings(
        findings=findings,
        risk_score=0.3,
        confidence=0.85,
        risk_tier="low",
    )


async def run_research(job_id: str, hop_token: str) -> None:
    """Execute the full research flow for a job.

    Called by the broker worker after verifying the hop token.

    Path C (Registry → Research Agent):
      1. Fetch model architectures from Firestore model_registry (internal read).
      2. Fetch job context from Firestore jobs/{id} (internal read).
      3. Combine into registry_context payload.

    Path B continues:
      4. Call the research agent with the hop token + full context.
      5. Agent analyzes prompt + available architectures via Gemini.
      6. Agent proposes or selects architecture + returns findings.
      7. Store findings on the job doc.
      8. Advance job status to awaiting_approval.

    If the research agent fails, the job is set to awaiting_approval
    with high-risk findings to force human review (fail-safe).
    """
    # ── Path C: Internal registry read (no token needed, backend-internal) ────
    model_architectures = fetch_model_registry()
    logger.info(
        "Job %s: fetched %d model architectures from registry (Path C)",
        job_id,
        len(model_architectures),
    )

    # Fetch job context for the research agent
    data = get_doc(COLLECTION, job_id)
    if data is None:
        logger.error("Research: job %s not found — cannot proceed", job_id)
        return

    # Build the full registry context (Path C data + job data)
    registry_context = {
        "prompt": data.get("prompt", ""),
        "dataset_object_path": data.get("dataset_object_path", ""),
        "available_architectures": model_architectures,
    }

    # ── Path B: Call research agent (hop token secures the boundary) ───────────
    result = await call_research_agent(job_id, hop_token, registry_context)

    # Store findings and advance to awaiting_approval
    update_doc(
        COLLECTION,
        job_id,
        {
            "status": JobStatus.awaiting_approval.value,
            "research_findings": result.findings,
            "risk_tier": result.risk_tier,
            "risk_score": result.risk_score,
            "risk_confidence": result.confidence,
            "risk_reasoning": (
                f"Risk tier: {result.risk_tier} (score: {result.risk_score:.2f}, "
                f"confidence: {result.confidence:.2f}). {result.findings[:200]}"
            ),
        },
    )
    logger.info(
        "Job %s: research complete → awaiting_approval (risk_tier=%s)",
        job_id,
        result.risk_tier,
    )
