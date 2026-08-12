"""Tests for V2 auth routes: register, login, logout, me.

All Firestore calls are mocked — no real Firebase connection required.
The dev-token fallback (ALLOW_DEV_TOKEN=true) is set in conftest so
all existing tests using Bearer dev-token-change-me continue to work.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

# ── Helpers ───────────────────────────────────────────────────────────────────

_REGISTER_PAYLOAD = {
    "email": "alice@example.com",
    "password": "securepass1",
    "display_name": "Alice",
}

_LOGIN_PAYLOAD = {
    "email": "alice@example.com",
    "password": "securepass1",
}

_FAKE_USER = {
    "id": "user_auth_001",
    "email": "alice@example.com",
    "password_hash": "",  # verify_password is mocked
    "display_name": "Alice",
    "is_active": True,
    "created_at": "2026-08-12T00:00:00+00:00",
}


def _mock_session_db():
    """Return a mock Firestore db that accepts session writes."""
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.set.return_value = None
    return mock_db


# ── POST /auth/register ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_returns_201(client: AsyncClient):
    with (
        patch("src.routes.auth_routes.db_users.get_user_by_email", return_value=None),
        patch("src.routes.auth_routes.db_users.create_user", return_value="user_new_001"),
        patch("src.db.sessions.db", _mock_session_db()),
    ):
        resp = await client.post("/auth/register", json=_REGISTER_PAYLOAD)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_register_response_has_access_token(client: AsyncClient):
    with (
        patch("src.routes.auth_routes.db_users.get_user_by_email", return_value=None),
        patch("src.routes.auth_routes.db_users.create_user", return_value="user_new_002"),
        patch("src.db.sessions.db", _mock_session_db()),
    ):
        resp = await client.post("/auth/register", json=_REGISTER_PAYLOAD)
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in"], int)
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient):
    with patch("src.routes.auth_routes.db_users.get_user_by_email", return_value=_FAKE_USER):
        resp = await client.post("/auth/register", json=_REGISTER_PAYLOAD)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(client: AsyncClient):
    payload = {**_REGISTER_PAYLOAD, "email": "not-an-email"}
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password_returns_422(client: AsyncClient):
    payload = {**_REGISTER_PAYLOAD, "password": "short"}
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_display_name_returns_422(client: AsyncClient):
    payload = {"email": "bob@example.com", "password": "goodpassword1"}
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 422


# ── POST /auth/login ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success_returns_200(client: AsyncClient):
    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=_FAKE_USER),
        patch("src.services.auth_service.verify_password", return_value=True),
        patch("src.db.sessions.db", _mock_session_db()),
    ):
        resp = await client.post("/auth/login", json=_LOGIN_PAYLOAD)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_success_response_shape(client: AsyncClient):
    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=_FAKE_USER),
        patch("src.services.auth_service.verify_password", return_value=True),
        patch("src.db.sessions.db", _mock_session_db()),
    ):
        resp = await client.post("/auth/login", json=_LOGIN_PAYLOAD)
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in"], int)


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient):
    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=_FAKE_USER),
        patch("src.services.auth_service.verify_password", return_value=False),
    ):
        resp = await client.post("/auth/login", json=_LOGIN_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client: AsyncClient):
    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=None):
        resp = await client.post("/auth/login", json=_LOGIN_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_and_missing_return_same_status(client: AsyncClient):
    """No user enumeration: wrong password and missing user both return 401."""
    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=_FAKE_USER),
        patch("src.services.auth_service.verify_password", return_value=False),
    ):
        resp_wrong = await client.post("/auth/login", json=_LOGIN_PAYLOAD)

    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=None):
        resp_missing = await client.post("/auth/login", json=_LOGIN_PAYLOAD)

    assert resp_wrong.status_code == 401
    assert resp_missing.status_code == 401


# ── POST /auth/logout ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_logout_returns_204(client: AsyncClient, auth_headers: dict):
    with patch("src.routes.auth_routes.invalidate_session"):
        resp = await client.post("/auth/logout", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_logout_no_token_returns_401(client: AsyncClient):
    resp = await client.post("/auth/logout")
    assert resp.status_code == 401


# ── GET /auth/me ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_returns_user_profile(client: AsyncClient, auth_headers: dict):
    with patch("src.routes.auth_routes.db_users.get_user_by_id", return_value=_FAKE_USER):
        resp = await client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["display_name"] == "Alice"
    assert "password" not in body
    assert "password_hash" not in body


@pytest.mark.asyncio
async def test_me_no_token_returns_401(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_expired_session_returns_401(client: AsyncClient):
    """A valid-format token that doesn't match any session returns 401."""
    headers = {"Authorization": "Bearer totally-invalid-token-xyz"}
    with patch("src.middleware.auth.db_sessions.get_session_by_token_hash", return_value=None):
        resp = await client.get("/auth/me", headers=headers)
    assert resp.status_code == 401
