"""Tests for the Bearer token prefix stripping fix in require_auth.

Validates that:
- Token without "Bearer" prefix works (normal usage).
- Token WITH "Bearer" prefix works (Swagger UI mistake).
- Token with "bearer" (lowercase) prefix works.
- Empty token after stripping still fails.
- Dev-token path works with and without prefix when ALLOW_DEV_TOKEN=true.
- Real session path works with and without prefix.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient

_USER_ID = "user_bearer_test"
_FAKE_USER = {
    "id": _USER_ID,
    "email": "bearer@terafac.dev",
    "password_hash": "",
    "display_name": "Bearer Test User",
    "is_active": True,
    "created_at": "2026-08-12T00:00:00+00:00",
}


def _future_session(user_id: str = _USER_ID) -> dict:
    """Return a valid, non-expired session doc."""
    future = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    return {
        "user_id": user_id,
        "expires_at": future,
        "revoked": False,
    }


# ── Dev-token path ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dev_token_without_prefix(client: AsyncClient):
    """Standard dev-token usage: just the token value, no 'Bearer' prefix."""
    headers = {"Authorization": "Bearer dev-token-change-me"}
    resp = await client.get("/health", headers=headers)
    # /health doesn't require auth, but let's test a protected endpoint.
    resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dev_token_with_bearer_prefix_in_value(client: AsyncClient):
    """Swagger UI mistake: user pastes 'Bearer dev-token-change-me' into dialog.

    The actual Authorization header becomes: 'Bearer Bearer dev-token-change-me'.
    HTTPBearer parses this as credentials='Bearer dev-token-change-me'.
    Our fix must strip the prefix and match the dev-token.
    """
    headers = {"Authorization": "Bearer Bearer dev-token-change-me"}
    resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dev_token_with_lowercase_bearer_prefix(client: AsyncClient):
    """User pastes 'bearer dev-token-change-me' (lowercase)."""
    headers = {"Authorization": "Bearer bearer dev-token-change-me"}
    resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 200


# ── Real session path with prefix ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_real_session_token_without_prefix(client: AsyncClient):
    """Normal flow: token is just the raw session value."""
    with (
        patch(
            "src.middleware.auth.db_sessions.get_session_by_token_hash",
            return_value=_future_session(),
        ),
        patch("src.middleware.auth.db_users.get_user_by_id", return_value=_FAKE_USER),
    ):
        headers = {"Authorization": "Bearer actual-session-token-xyz"}
        resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_real_session_token_with_bearer_prefix(client: AsyncClient):
    """Swagger UI mistake: pasted 'Bearer actual-session-token-xyz'.

    After stripping, the middleware should hash 'actual-session-token-xyz'
    and find the session.
    """
    with (
        patch(
            "src.middleware.auth.db_sessions.get_session_by_token_hash",
            return_value=_future_session(),
        ),
        patch("src.middleware.auth.db_users.get_user_by_id", return_value=_FAKE_USER),
    ):
        # Double-Bearer scenario
        headers = {"Authorization": "Bearer Bearer actual-session-token-xyz"}
        resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 200


# ── Edge cases ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_token_returns_401(client: AsyncClient):
    """Empty Authorization value must still fail."""
    headers = {"Authorization": "Bearer "}
    resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bearer_only_returns_401(client: AsyncClient):
    """Token is literally just 'Bearer' (nothing after stripping)."""
    headers = {"Authorization": "Bearer Bearer"}
    resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_returns_401(client: AsyncClient):
    """Invalid token that doesn't match dev-token or any session."""
    with patch("src.middleware.auth.db_sessions.get_session_by_token_hash", return_value=None):
        headers = {"Authorization": "Bearer invalid-garbage-token"}
        resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_no_auth_header_returns_401(client: AsyncClient):
    """No Authorization header at all must fail."""
    resp = await client.get("/jobs")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_session_returns_401(client: AsyncClient):
    """A valid-format token with an expired session must fail."""
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    expired_session = {
        "user_id": _USER_ID,
        "expires_at": past,
        "revoked": False,
    }
    with patch(
        "src.middleware.auth.db_sessions.get_session_by_token_hash",
        return_value=expired_session,
    ):
        headers = {"Authorization": "Bearer some-expired-token"}
        resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_revoked_session_returns_401(client: AsyncClient):
    """A revoked session must fail even if not expired."""
    future = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    revoked_session = {
        "user_id": _USER_ID,
        "expires_at": future,
        "revoked": True,
    }
    with patch(
        "src.middleware.auth.db_sessions.get_session_by_token_hash",
        return_value=revoked_session,
    ):
        headers = {"Authorization": "Bearer some-revoked-token"}
        resp = await client.get("/jobs", headers=headers)
    assert resp.status_code == 401
