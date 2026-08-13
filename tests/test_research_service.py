"""V4: Research service tests.

Tests cover:
- ResearchFindings container
- _stub_research returns canned findings
- call_research_agent falls back to stub when no GEMINI_API_KEY
- call_research_agent calls real endpoint when GEMINI_API_KEY set
- call_research_agent handles network failure (returns high-risk fallback)
- run_research fetches job context, calls research agent, updates Firestore
- run_research handles missing job gracefully
- Audit trail: hop_token_issued for research step logged correctly
- Broker dispatches research task on annotations submit
- Integration: annotations → researching → research completes → awaiting_approval
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.fe_contract import AnnotationsResponse

# ── ResearchFindings ──────────────────────────────────────────────────────────


def test_research_findings_container():
    from src.services.research_service import ResearchFindings

    rf = ResearchFindings(
        findings="test findings",
        risk_score=0.5,
        confidence=0.8,
        risk_tier="medium",
    )
    assert rf.findings == "test findings"
    assert rf.risk_score == 0.5
    assert rf.confidence == 0.8
    assert rf.risk_tier == "medium"


# ── Stub research ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stub_research_returns_findings():
    """The local dev stub returns canned findings after a delay."""
    # Monkeypatch the delay to make the test fast
    import src.services.research_service as rs
    from src.services.research_service import _stub_research

    original_delay = rs.RESEARCH_STUB_DELAY
    rs.RESEARCH_STUB_DELAY = 0.01
    try:
        result = await _stub_research("job_123", {"prompt": "train on my dataset"})
        assert result.findings
        assert "job_123" in result.findings
        assert "train on my dataset" in result.findings
        assert result.risk_tier == "low"
        assert 0.0 <= result.risk_score <= 1.0
        assert 0.0 <= result.confidence <= 1.0
    finally:
        rs.RESEARCH_STUB_DELAY = original_delay


@pytest.mark.asyncio
async def test_stub_research_without_context():
    """Stub works when no registry context is provided."""
    import src.services.research_service as rs

    original_delay = rs.RESEARCH_STUB_DELAY
    rs.RESEARCH_STUB_DELAY = 0.01
    try:
        result = await rs._stub_research("job_456", None)
        assert result.findings
        assert "job_456" in result.findings
        assert result.risk_tier == "low"
    finally:
        rs.RESEARCH_STUB_DELAY = original_delay


# ── call_research_agent ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_research_agent_uses_stub_when_no_gemini_key():
    """When GEMINI_API_KEY is empty, call_research_agent falls back to stub."""
    import src.services.research_service as rs

    original_delay = rs.RESEARCH_STUB_DELAY
    rs.RESEARCH_STUB_DELAY = 0.01
    try:
        with patch.object(rs.get_settings(), "gemini_api_key", ""):
            result = await rs.call_research_agent("job_789", "fake-token", {"prompt": "test"})
            assert result.findings
            assert result.risk_tier == "low"
    finally:
        rs.RESEARCH_STUB_DELAY = original_delay


@pytest.mark.asyncio
async def test_call_research_agent_calls_real_endpoint():
    """When GEMINI_API_KEY is set, call_research_agent POSTs to the research URL."""
    import src.services.research_service as rs

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "findings": "Real findings from Gemini",
        "risk_score": 0.4,
        "confidence": 0.9,
        "risk_tier": "low",
    }

    mock_settings = MagicMock()
    mock_settings.gemini_api_key = "test-gemini-key"
    mock_settings.research_agent_url = "http://research-agent:8001/run"
    mock_settings.research_timeout_seconds = 10

    with patch.object(rs, "get_settings", return_value=mock_settings):
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await rs.call_research_agent("job_001", "hop-token-jwt", {"prompt": "x"})

    assert result.findings == "Real findings from Gemini"
    assert result.risk_score == 0.4
    assert result.confidence == 0.9
    assert result.risk_tier == "low"


@pytest.mark.asyncio
async def test_call_research_agent_handles_network_failure():
    """On network failure, returns high-risk fallback to force manual review."""
    import src.services.research_service as rs

    mock_settings = MagicMock()
    mock_settings.gemini_api_key = "test-gemini-key"
    mock_settings.research_agent_url = "http://research-agent:8001/run"
    mock_settings.research_timeout_seconds = 1

    with patch.object(rs, "get_settings", return_value=mock_settings):
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await rs.call_research_agent("job_001", "hop-token-jwt", {})

    assert result.risk_tier == "high"
    assert result.confidence == 0.1
    assert "unreachable" in result.findings.lower() or "manual review" in result.findings.lower()


# ── run_research ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_research_updates_firestore_on_success():
    """run_research fetches job, calls agent, writes findings to Firestore."""
    import src.services.research_service as rs

    job_data = {
        "prompt": "train segmentation",
        "dataset_object_path": "datasets/ds_001/raw.zip",
        "flagged_images": [],
    }

    mock_findings = rs.ResearchFindings(
        findings="Everything looks safe",
        risk_score=0.2,
        confidence=0.9,
        risk_tier="low",
    )

    with (
        patch.object(rs, "get_doc", return_value=job_data) as mock_get,
        patch.object(rs, "update_doc") as mock_update,
        patch.object(rs, "call_research_agent", return_value=mock_findings) as mock_call,
    ):
        await rs.run_research("job_001", "fake-hop-token")

    mock_get.assert_called_once_with("jobs", "job_001")
    mock_call.assert_called_once()
    # Verify the call included the job context
    call_args = mock_call.call_args
    assert call_args[0][0] == "job_001"  # job_id
    assert call_args[0][1] == "fake-hop-token"  # hop_token
    assert call_args[0][2]["prompt"] == "train segmentation"

    # Verify Firestore was updated with findings
    mock_update.assert_called_once()
    update_call = mock_update.call_args[0]
    assert update_call[0] == "jobs"
    assert update_call[1] == "job_001"
    payload = update_call[2]
    assert payload["status"] == "awaiting_approval"
    assert payload["research_findings"] == "Everything looks safe"
    assert payload["risk_tier"] == "low"
    assert payload["risk_score"] == 0.2
    assert payload["risk_confidence"] == 0.9
    assert "risk_reasoning" in payload


@pytest.mark.asyncio
async def test_run_research_handles_missing_job():
    """run_research returns silently when job doesn't exist."""
    import src.services.research_service as rs

    with (
        patch.object(rs, "get_doc", return_value=None),
        patch.object(rs, "update_doc") as mock_update,
        patch.object(rs, "call_research_agent") as mock_call,
    ):
        await rs.run_research("missing_job", "fake-hop-token")

    mock_call.assert_not_called()
    mock_update.assert_not_called()


# ── Integration: annotations → research dispatch ──────────────────────────────


@pytest.mark.asyncio
async def test_annotations_route_dispatches_research_hop(client, auth_headers):
    """POST /jobs/{id}/annotations dispatches a research-scoped broker task."""
    from src.services.broker import set_broker

    mock_broker = MagicMock()
    mock_broker.enqueue = AsyncMock(return_value="task_job_001_research")
    set_broker(mock_broker)

    try:
        with patch(
            "src.routes.job_action_routes.job_service.submit_annotations",
            return_value=AnnotationsResponse(ok=True, stage="researching"),
        ):
            resp = await client.post(
                "/jobs/job_001/annotations",
                json={"ack": True},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        # Verify broker was called with a research task
        mock_broker.enqueue.assert_called_once()
        task = mock_broker.enqueue.call_args[0][0]
        assert task.job_id == "job_001"
        assert task.task_type == "research"
        assert task.hop_token  # non-empty JWT
    finally:
        # Reset broker singleton
        from src.services.broker import InMemoryBroker

        set_broker(InMemoryBroker())


@pytest.mark.asyncio
async def test_research_hop_token_has_correct_step_claim():
    """The hop token issued for research has step='research' claim."""
    from src.services.jwt_hop import issue_hop_token, verify_hop_token

    token = issue_hop_token("job_test_001", step="research")
    claims = verify_hop_token(token, expected_step="research")
    assert claims["sub"] == "job_test_001"
    assert claims["step"] == "research"
    assert claims["iss"] == "terafac-api"
    assert claims["aud"] == "terafac-worker"


@pytest.mark.asyncio
async def test_research_hop_token_rejected_for_wrong_step():
    """A research hop token cannot be used for training or pre_masking."""
    from fastapi import HTTPException

    from src.services.jwt_hop import issue_hop_token, verify_hop_token

    token = issue_hop_token("job_test_002", step="research")

    with pytest.raises(HTTPException) as exc_info:
        verify_hop_token(token, expected_step="training")
    assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info:
        verify_hop_token(token, expected_step="pre_masking")
    assert exc_info.value.status_code == 401


# ── Job status: researching stage ─────────────────────────────────────────────


def test_job_status_has_researching():
    """JobStatus enum includes 'researching' as a valid state."""
    from src.schemas.job import JobStatus

    assert hasattr(JobStatus, "researching")
    assert JobStatus.researching.value == "researching"


def test_progress_for_researching_stage():
    """The researching stage maps to 60% progress."""
    from src.services.job_service import _compute_progress

    assert _compute_progress("researching", None, None) == 60


# ── Config: research settings ─────────────────────────────────────────────────


def test_config_has_research_agent_url(settings):
    """Settings includes research_agent_url field."""
    assert hasattr(settings, "research_agent_url")
    assert settings.research_agent_url  # non-empty default


def test_config_has_gemini_api_key_field(settings):
    """Settings includes gemini_api_key field (empty by default for stub mode)."""
    assert hasattr(settings, "gemini_api_key")


def test_config_has_research_timeout(settings):
    """Settings includes research_timeout_seconds field."""
    assert hasattr(settings, "research_timeout_seconds")
    assert settings.research_timeout_seconds > 0


# ── JobProgress includes research findings ────────────────────────────────────


def test_job_progress_includes_research_fields():
    """JobProgress schema has research_findings, risk_tier, risk_reasoning fields."""
    from src.schemas.fe_contract import JobProgress

    jp = JobProgress(
        stage="awaiting_approval",
        progress=75,
        research_findings="Agent found no issues",
        risk_tier="low",
        risk_reasoning="Score 0.2, confidence 0.9",
    )
    assert jp.research_findings == "Agent found no issues"
    assert jp.risk_tier == "low"
    assert jp.risk_reasoning == "Score 0.2, confidence 0.9"


def test_job_progress_research_fields_optional():
    """Research fields default to None when not provided."""
    from src.schemas.fe_contract import JobProgress

    jp = JobProgress(stage="pre_masking", progress=25)
    assert jp.research_findings is None
    assert jp.risk_tier is None
    assert jp.risk_reasoning is None
