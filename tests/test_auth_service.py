"""Tests for src/services/auth_service.py and supporting db helpers.

All Firestore calls are intercepted by the conftest mock — no real Firebase
connection is made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.auth_service import (
    authenticate_user,
    create_user_session,
    hash_password,
    invalidate_session,
    verify_password,
)

# ── hash_password ──────────────────────────────────────────────────────────────


def test_hash_password_returns_bcrypt_string():
    hashed = hash_password("mypassword123")
    assert hashed.startswith("$2b$")


def test_hash_password_minimum_rounds():
    hashed = hash_password("mypassword123")
    # The work factor is encoded in the hash — must be at least 12.
    cost_factor = int(hashed.split("$")[2])
    assert cost_factor >= 12


def test_hash_password_different_calls_produce_different_hashes():
    h1 = hash_password("samepassword")
    h2 = hash_password("samepassword")
    # bcrypt uses random salt — same input must NOT produce same output.
    assert h1 != h2


def test_hash_password_never_equals_plaintext():
    plain = "supersecret"
    hashed = hash_password(plain)
    assert hashed != plain


# ── verify_password ────────────────────────────────────────────────────────────


def test_verify_password_correct():
    plain = "correctpassword"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("rightpassword")
    assert verify_password("wrongpassword", hashed) is False


def test_verify_password_malformed_hash_returns_false():
    # Should not raise — just return False.
    assert verify_password("anything", "notahash") is False


def test_verify_password_empty_plain_false():
    hashed = hash_password("notempty")
    assert verify_password("", hashed) is False


# ── authenticate_user ──────────────────────────────────────────────────────────


def test_authenticate_user_success():
    plain = "validpassword1"
    hashed = hash_password(plain)
    fake_user = {
        "id": "user_abc",
        "email": "test@example.com",
        "password_hash": hashed,
        "is_active": True,
    }
    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=fake_user):
        result = authenticate_user("test@example.com", plain)
    assert result is not None
    assert result["id"] == "user_abc"


def test_authenticate_user_wrong_password():
    hashed = hash_password("correctpassword")
    fake_user = {
        "id": "user_abc",
        "email": "test@example.com",
        "password_hash": hashed,
        "is_active": True,
    }
    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=fake_user):
        result = authenticate_user("test@example.com", "wrongpassword")
    assert result is None


def test_authenticate_user_not_found():
    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=None):
        result = authenticate_user("nobody@example.com", "password")
    assert result is None


def test_authenticate_user_inactive_account():
    hashed = hash_password("mypassword")
    fake_user = {
        "id": "user_xyz",
        "email": "inactive@example.com",
        "password_hash": hashed,
        "is_active": False,
    }
    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=fake_user):
        result = authenticate_user("inactive@example.com", "mypassword")
    assert result is None


def test_authenticate_user_same_error_message_missing_vs_wrong_password(monkeypatch):
    """Both 'user not found' and 'wrong password' must return None — no distinction."""
    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=None):
        result_missing = authenticate_user("ghost@example.com", "any")

    hashed = hash_password("correctpwd")
    fake_user = {
        "id": "u1",
        "email": "real@example.com",
        "password_hash": hashed,
        "is_active": True,
    }
    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=fake_user):
        result_wrong = authenticate_user("real@example.com", "wrongpwd")

    assert result_missing is None
    assert result_wrong is None


# ── create_user_session ────────────────────────────────────────────────────────


def test_create_user_session_returns_token_string():
    mock_db = MagicMock()
    with patch("src.db.sessions.db", mock_db):
        token = create_user_session("user_123")
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_user_session_token_is_urlsafe():
    import re

    mock_db = MagicMock()
    with patch("src.db.sessions.db", mock_db):
        token = create_user_session("user_123")
    # secrets.token_urlsafe produces base64url chars + padding stripped
    assert re.match(r"^[A-Za-z0-9_\-]+$", token)


def test_create_user_session_different_tokens_each_call():
    mock_db = MagicMock()
    with patch("src.db.sessions.db", mock_db):
        t1 = create_user_session("user_123")
        t2 = create_user_session("user_123")
    assert t1 != t2


def test_create_user_session_writes_to_firestore():
    mock_db = MagicMock()
    with patch("src.db.sessions.db", mock_db):
        create_user_session("user_abc")
    # db.collection(...).document(...).set(...) must have been called once
    mock_db.collection.assert_called_with("sessions")
    mock_db.collection.return_value.document.return_value.set.assert_called_once()


def test_create_user_session_stores_correct_user_id():
    mock_db = MagicMock()
    with patch("src.db.sessions.db", mock_db):
        create_user_session("user_42")
    call_args = mock_db.collection.return_value.document.return_value.set.call_args
    stored_data = call_args[0][0]
    assert stored_data["user_id"] == "user_42"
    assert stored_data["revoked"] is False
    assert "expires_at" in stored_data
    assert "created_at" in stored_data


# ── invalidate_session ────────────────────────────────────────────────────────


def test_invalidate_session_calls_delete():
    with (
        patch("src.services.auth_service.db_sessions.delete_session") as mock_del,
        patch("src.services.auth_service.db_sessions.hash_token", return_value="fakehash"),
    ):
        invalidate_session("raw-token-value")
    mock_del.assert_called_once_with("fakehash")


def test_invalidate_session_does_not_log_raw_token(caplog):
    raw = "super-secret-raw-token"
    with (
        patch("src.services.auth_service.db_sessions.delete_session"),
        patch("src.db.sessions.delete_doc"),
    ):
        invalidate_session(raw)
    # Raw token must NOT appear in any log output.
    assert raw not in caplog.text
