"""V3-M4: Unit tests for src/services/audit.py.

Covers:
    - log_hop_issued writes correct fields to audit_log collection
    - log_hop_issued never includes raw token string
    - log_hop_verified writes correct fields to audit_log collection
    - log_hop_verified never includes raw token string
    - audit writes are best-effort: Firestore failure does not raise
    - issue_hop_token calls log_hop_issued (wired correctly in jwt_hop.py)
    - verify_hop_token calls log_hop_verified (wired correctly in jwt_hop.py)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.services.audit import COLLECTION, log_hop_issued, log_hop_verified

# ---------------------------------------------------------------------------
# log_hop_issued
# ---------------------------------------------------------------------------


def test_log_hop_issued_writes_to_audit_log_collection():
    """log_hop_issued must call create_doc with collection='audit_log'."""
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_issued("job_001", "pre_masking", issued_at=1000, expires_at=1300)

    mock_create.assert_called_once()
    coll = mock_create.call_args[0][0]
    assert coll == COLLECTION


def test_log_hop_issued_writes_correct_event_field():
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_issued("job_001", "pre_masking", issued_at=1000, expires_at=1300)

    doc = mock_create.call_args[0][1]
    assert doc["event"] == "hop_token_issued"


def test_log_hop_issued_writes_job_id_and_step():
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_issued("job_audit_01", "training", issued_at=2000, expires_at=2300)

    doc = mock_create.call_args[0][1]
    assert doc["job_id"] == "job_audit_01"
    assert doc["step"] == "training"


def test_log_hop_issued_writes_timestamps():
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_issued("job_001", "pre_masking", issued_at=1111, expires_at=1411)

    doc = mock_create.call_args[0][1]
    assert doc["issued_at"] == 1111
    assert doc["expires_at"] == 1411


def test_log_hop_issued_includes_server_timestamp():
    """The 'ts' field must be present (SERVER_TIMESTAMP sentinel)."""
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_issued("job_001", "pre_masking", issued_at=1000, expires_at=1300)

    doc = mock_create.call_args[0][1]
    assert "ts" in doc


def test_log_hop_issued_does_not_include_raw_token():
    """The audit document must not contain a 'token' or 'hop_token' field."""
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_issued("job_001", "pre_masking", issued_at=1000, expires_at=1300)

    doc = mock_create.call_args[0][1]
    assert "token" not in doc
    assert "hop_token" not in doc
    assert "jwt" not in doc


def test_log_hop_issued_is_best_effort_on_firestore_error():
    """A Firestore failure in log_hop_issued must not raise — best-effort write."""
    with patch("src.services.audit.create_doc", side_effect=Exception("Firestore down")):
        # Must not raise
        log_hop_issued("job_001", "pre_masking", issued_at=1000, expires_at=1300)


# ---------------------------------------------------------------------------
# log_hop_verified
# ---------------------------------------------------------------------------


def test_log_hop_verified_writes_to_audit_log_collection():
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_verified("job_002", "training")

    mock_create.assert_called_once()
    coll = mock_create.call_args[0][0]
    assert coll == COLLECTION


def test_log_hop_verified_writes_correct_event_field():
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_verified("job_002", "training")

    doc = mock_create.call_args[0][1]
    assert doc["event"] == "hop_token_verified"


def test_log_hop_verified_writes_job_id_and_step():
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_verified("job_verify_01", "pre_masking")

    doc = mock_create.call_args[0][1]
    assert doc["job_id"] == "job_verify_01"
    assert doc["step"] == "pre_masking"


def test_log_hop_verified_includes_server_timestamp():
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_verified("job_002", "training")

    doc = mock_create.call_args[0][1]
    assert "ts" in doc


def test_log_hop_verified_does_not_include_raw_token():
    """Verified audit entries must never contain the raw token string."""
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_verified("job_002", "training")

    doc = mock_create.call_args[0][1]
    assert "token" not in doc
    assert "hop_token" not in doc
    assert "jwt" not in doc


def test_log_hop_verified_does_not_include_issued_at_or_expires_at():
    """Verified entries only need event/job_id/step/ts — no timestamp fields."""
    with patch("src.services.audit.create_doc") as mock_create:
        log_hop_verified("job_002", "training")

    doc = mock_create.call_args[0][1]
    assert "issued_at" not in doc
    assert "expires_at" not in doc


def test_log_hop_verified_is_best_effort_on_firestore_error():
    """A Firestore failure in log_hop_verified must not raise."""
    with patch("src.services.audit.create_doc", side_effect=Exception("Firestore down")):
        log_hop_verified("job_002", "training")


# ---------------------------------------------------------------------------
# Wiring: issue_hop_token calls log_hop_issued
# ---------------------------------------------------------------------------


def test_issue_hop_token_calls_log_hop_issued():
    """issue_hop_token must call log_hop_issued after minting the token."""
    with patch("src.services.jwt_hop.log_hop_issued") as mock_issued:
        from src.services.jwt_hop import issue_hop_token

        issue_hop_token("job_wire_01", "pre_masking")

    mock_issued.assert_called_once()
    kwargs = mock_issued.call_args
    # Positional: job_id, step, issued_at=, expires_at=
    assert kwargs[0][0] == "job_wire_01"
    assert kwargs[0][1] == "pre_masking"
    assert "issued_at" in kwargs[1]
    assert "expires_at" in kwargs[1]


def test_issue_hop_token_does_not_pass_raw_token_to_audit():
    """issue_hop_token must never pass the raw JWT to log_hop_issued."""
    captured_args = []

    def capture(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured_args.append((args, kwargs))

    with patch("src.services.jwt_hop.log_hop_issued", side_effect=capture):
        from src.services.jwt_hop import issue_hop_token

        token = issue_hop_token("job_wire_02", "training")

    # The raw token must not appear anywhere in the captured audit call
    all_arg_strings = str(captured_args)
    assert token not in all_arg_strings


# ---------------------------------------------------------------------------
# Wiring: verify_hop_token calls log_hop_verified
# ---------------------------------------------------------------------------


def test_verify_hop_token_calls_log_hop_verified():
    """verify_hop_token must call log_hop_verified on successful verification."""
    from src.services.jwt_hop import issue_hop_token, verify_hop_token

    token = issue_hop_token("job_wire_03", "training")

    with patch("src.services.jwt_hop.log_hop_verified") as mock_verified:
        verify_hop_token(token, expected_step="training")

    mock_verified.assert_called_once_with("job_wire_03", "training")


def test_verify_hop_token_does_not_call_log_hop_verified_on_failure():
    """verify_hop_token must NOT call log_hop_verified when verification fails."""
    from fastapi import HTTPException

    from src.services.jwt_hop import verify_hop_token

    with (
        patch("src.services.jwt_hop.log_hop_verified") as mock_verified,
        pytest.raises(HTTPException),
    ):
        verify_hop_token("garbage.token.string", expected_step="pre_masking")

    mock_verified.assert_not_called()
