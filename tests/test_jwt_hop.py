"""V3-M1: Unit tests for src/services/jwt_hop.py.

Covers:
    - issue_hop_token produces a valid, decodable JWT with correct claims
    - verify_hop_token accepts a valid token and returns the payload
    - verify_hop_token raises 401 on expired token
    - verify_hop_token raises 401 on wrong step
    - verify_hop_token raises 401 on wrong signature (tampered key)
    - verify_hop_token raises 401 on wrong audience
    - verify_hop_token raises 401 on wrong issuer
    - Raw token string is never present in log output (metadata-only logging)
    - issue_hop_token uses the configured TTL for expiry
    - verify_hop_token returns the full payload dict on success
"""

from __future__ import annotations

import logging
import time

import jwt
import pytest

from src.config import Settings, get_settings
from src.services.jwt_hop import issue_hop_token, verify_hop_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-jwt-hop-secret-for-pytest-minimum-32-chars!!"
_TEST_JOB_ID = "job_test_001"
_TEST_STEP = "pre_masking"


def _decode_raw(token: str, settings: Settings) -> dict:
    """Decode without verification — used only to inspect raw claims in tests."""
    return jwt.decode(
        token,
        settings.jwt_hop_secret,
        algorithms=["HS256"],
        audience=settings.jwt_hop_audience,
    )


# ---------------------------------------------------------------------------
# issue_hop_token tests
# ---------------------------------------------------------------------------


def test_issue_returns_string():
    """issue_hop_token must return a non-empty string."""
    token = issue_hop_token(_TEST_JOB_ID, _TEST_STEP)
    assert isinstance(token, str)
    assert len(token) > 0


def test_issued_token_has_correct_sub_claim():
    settings = get_settings()
    token = issue_hop_token(_TEST_JOB_ID, _TEST_STEP)
    payload = _decode_raw(token, settings)
    assert payload["sub"] == _TEST_JOB_ID


def test_issued_token_has_correct_step_claim():
    settings = get_settings()
    token = issue_hop_token(_TEST_JOB_ID, _TEST_STEP)
    payload = _decode_raw(token, settings)
    assert payload["step"] == _TEST_STEP


def test_issued_token_has_correct_issuer():
    settings = get_settings()
    token = issue_hop_token(_TEST_JOB_ID, _TEST_STEP)
    payload = _decode_raw(token, settings)
    assert payload["iss"] == settings.jwt_hop_issuer


def test_issued_token_has_correct_audience():
    settings = get_settings()
    token = issue_hop_token(_TEST_JOB_ID, _TEST_STEP)
    payload = _decode_raw(token, settings)
    assert payload["aud"] == settings.jwt_hop_audience


def test_issued_token_expiry_matches_ttl():
    """exp - iat must equal jwt_hop_ttl_seconds (within 2s clock tolerance)."""
    settings = get_settings()
    token = issue_hop_token(_TEST_JOB_ID, _TEST_STEP)
    payload = _decode_raw(token, settings)
    delta = payload["exp"] - payload["iat"]
    assert abs(delta - settings.jwt_hop_ttl_seconds) <= 2


def test_issue_different_steps_produce_different_tokens():
    """Tokens for different steps must differ."""
    t1 = issue_hop_token(_TEST_JOB_ID, "pre_masking")
    t2 = issue_hop_token(_TEST_JOB_ID, "training")
    assert t1 != t2


# ---------------------------------------------------------------------------
# verify_hop_token — happy path
# ---------------------------------------------------------------------------


def test_verify_valid_token_returns_payload():
    """verify_hop_token returns a dict with correct claims for a valid token."""
    token = issue_hop_token(_TEST_JOB_ID, _TEST_STEP)
    payload = verify_hop_token(token, expected_step=_TEST_STEP)
    assert payload["sub"] == _TEST_JOB_ID
    assert payload["step"] == _TEST_STEP


def test_verify_training_step_token():
    """Verify a training-step token accepted with expected_step='training'."""
    token = issue_hop_token("job_002", "training")
    payload = verify_hop_token(token, expected_step="training")
    assert payload["sub"] == "job_002"
    assert payload["step"] == "training"


# ---------------------------------------------------------------------------
# verify_hop_token — rejection cases (all must return 401)
# ---------------------------------------------------------------------------


def test_verify_expired_token_raises_401():
    """An expired token must be rejected with HTTP 401."""
    settings = get_settings()
    past = int(time.time()) - 600  # issued 10 minutes ago
    payload = {
        "sub": _TEST_JOB_ID,
        "step": _TEST_STEP,
        "iat": past,
        "exp": past + 1,  # already expired
        "iss": settings.jwt_hop_issuer,
        "aud": settings.jwt_hop_audience,
    }
    expired_token = jwt.encode(payload, settings.jwt_hop_secret, algorithm="HS256")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        verify_hop_token(expired_token, expected_step=_TEST_STEP)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_verify_wrong_step_raises_401():
    """A valid token presented with the wrong expected_step must be rejected."""
    token = issue_hop_token(_TEST_JOB_ID, "pre_masking")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        verify_hop_token(token, expected_step="training")
    assert exc_info.value.status_code == 401
    assert "step" in exc_info.value.detail.lower()


def test_verify_wrong_signature_raises_401():
    """A token signed with a different secret must be rejected."""
    wrong_secret = "wrong-secret-key-that-is-definitely-32-chars-long!!"
    settings = get_settings()
    payload = {
        "sub": _TEST_JOB_ID,
        "step": _TEST_STEP,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "iss": settings.jwt_hop_issuer,
        "aud": settings.jwt_hop_audience,
    }
    bad_token = jwt.encode(payload, wrong_secret, algorithm="HS256")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        verify_hop_token(bad_token, expected_step=_TEST_STEP)
    assert exc_info.value.status_code == 401


def test_verify_wrong_audience_raises_401():
    """A token with a mismatched audience must be rejected."""
    settings = get_settings()
    payload = {
        "sub": _TEST_JOB_ID,
        "step": _TEST_STEP,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "iss": settings.jwt_hop_issuer,
        "aud": "wrong-audience",
    }
    bad_token = jwt.encode(payload, settings.jwt_hop_secret, algorithm="HS256")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        verify_hop_token(bad_token, expected_step=_TEST_STEP)
    assert exc_info.value.status_code == 401


def test_verify_wrong_issuer_raises_401():
    """A token with a mismatched issuer must be rejected."""
    settings = get_settings()
    payload = {
        "sub": _TEST_JOB_ID,
        "step": _TEST_STEP,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "iss": "rogue-issuer",
        "aud": settings.jwt_hop_audience,
    }
    bad_token = jwt.encode(payload, settings.jwt_hop_secret, algorithm="HS256")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        verify_hop_token(bad_token, expected_step=_TEST_STEP)
    assert exc_info.value.status_code == 401


def test_verify_garbage_token_raises_401():
    """A completely malformed token string must be rejected with 401."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        verify_hop_token("not.a.valid.jwt.at.all", expected_step=_TEST_STEP)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Security: raw token must never appear in log output
# ---------------------------------------------------------------------------


def test_issue_does_not_log_raw_token(caplog):
    """issue_hop_token must not write the raw token string to any log record."""
    with caplog.at_level(logging.DEBUG, logger="src.services.jwt_hop"):
        token = issue_hop_token(_TEST_JOB_ID, _TEST_STEP)
    # The raw token must not appear in any log message
    for record in caplog.records:
        assert token not in record.getMessage(), "Raw JWT found in log output — security violation"


def test_verify_does_not_log_raw_token(caplog):
    """verify_hop_token must not write the raw token string to any log record."""
    token = issue_hop_token(_TEST_JOB_ID, _TEST_STEP)
    with caplog.at_level(logging.DEBUG, logger="src.services.jwt_hop"):
        verify_hop_token(token, expected_step=_TEST_STEP)
    for record in caplog.records:
        assert token not in record.getMessage(), "Raw JWT found in log output — security violation"
