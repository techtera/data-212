"""Tests for src/middleware/rate_limit.py

Verifies the in-memory sliding-window IP rate limiter:
- Under the limit: requests succeed.
- At the limit: 6th attempt in window returns 429 with Retry-After header.
- After window expires: counter resets and requests succeed again.
- Reset helper clears state between tests.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from src.middleware.rate_limit import (
    check_login_rate_limit,
    reset_all_rate_limits,
    reset_rate_limit,
)


def _make_request(ip: str = "1.2.3.4") -> MagicMock:
    """Build a minimal mock Request with the given client IP."""
    req = MagicMock()
    req.headers = {}
    req.client = MagicMock()
    req.client.host = ip
    return req


@pytest.fixture(autouse=True)
def clean_buckets():
    """Reset all rate-limit buckets before every test in this module."""
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()


# ── Under the limit ───────────────────────────────────────────────────────────


def test_first_attempt_allowed():
    req = _make_request("10.0.0.1")
    # Should not raise.
    check_login_rate_limit(req)


def test_five_attempts_allowed():
    req = _make_request("10.0.0.2")
    for _ in range(5):
        check_login_rate_limit(req)  # must not raise


# ── At the limit ──────────────────────────────────────────────────────────────


def test_sixth_attempt_returns_429():
    req = _make_request("10.0.0.3")
    for _ in range(5):
        check_login_rate_limit(req)
    with pytest.raises(HTTPException) as exc_info:
        check_login_rate_limit(req)
    assert exc_info.value.status_code == 429


def test_429_has_retry_after_header():
    req = _make_request("10.0.0.4")
    for _ in range(5):
        check_login_rate_limit(req)
    with pytest.raises(HTTPException) as exc_info:
        check_login_rate_limit(req)
    assert "Retry-After" in exc_info.value.headers
    retry_after = int(exc_info.value.headers["Retry-After"])
    assert 0 < retry_after <= 61


def test_429_detail_message():
    req = _make_request("10.0.0.5")
    for _ in range(5):
        check_login_rate_limit(req)
    with pytest.raises(HTTPException) as exc_info:
        check_login_rate_limit(req)
    assert "Too many" in exc_info.value.detail


# ── Different IPs are independent ─────────────────────────────────────────────


def test_different_ips_have_independent_buckets():
    req_a = _make_request("192.168.1.1")
    req_b = _make_request("192.168.1.2")
    # Exhaust IP A.
    for _ in range(5):
        check_login_rate_limit(req_a)
    with pytest.raises(HTTPException):
        check_login_rate_limit(req_a)
    # IP B must still be allowed.
    check_login_rate_limit(req_b)  # must not raise


# ── Window reset ──────────────────────────────────────────────────────────────


def test_counter_resets_after_window(monkeypatch):
    """Simulate the 60-second window expiring by monkeypatching time.monotonic."""
    req = _make_request("10.0.0.6")
    call_count = 0
    base_time = 1000.0

    def fake_monotonic():
        # First 5 calls use base_time; subsequent calls add 61 s (outside window).
        nonlocal call_count
        call_count += 1
        if call_count <= 5:
            return base_time
        return base_time + 61.0

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    reset_rate_limit("10.0.0.6")

    for _ in range(5):
        check_login_rate_limit(req)

    # Next call is 61 s later — window has elapsed, should be allowed.
    check_login_rate_limit(req)  # must not raise


# ── X-Forwarded-For header ────────────────────────────────────────────────────


def test_x_forwarded_for_used_as_client_ip():
    """Rate limiter must use the leftmost X-Forwarded-For IP, not req.client.host."""
    req = MagicMock()
    req.headers = {"x-forwarded-for": "203.0.113.1, 10.0.0.1"}
    req.client = MagicMock()
    req.client.host = "10.0.0.1"  # proxy address — should NOT be used

    for _ in range(5):
        check_login_rate_limit(req)
    with pytest.raises(HTTPException):
        check_login_rate_limit(req)

    # Direct IP (10.0.0.1) should still be unaffected.
    req2 = _make_request("10.0.0.1")
    check_login_rate_limit(req2)  # must not raise


# ── Integration: POST /auth/login returns 429 via real router ─────────────────


@pytest.mark.asyncio
async def test_login_endpoint_returns_429_after_limit(client: AsyncClient):
    # V2 login uses email+password; use an invalid email to get consistent 401s
    # before the rate limit kicks in — the 422 from schema validation would also
    # consume a slot, but we want to exercise the 429 path clearly.
    payload = {"email": "test@example.com", "password": "wrongpass1"}
    headers = {"x-forwarded-for": "55.55.55.55"}

    with patch("src.services.auth_service.db_users.get_user_by_email", return_value=None):
        for _ in range(5):
            await client.post("/auth/login", json=payload, headers=headers)

        resp = await client.post("/auth/login", json=payload, headers=headers)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


@pytest.mark.asyncio
async def test_login_endpoint_allows_under_limit(client: AsyncClient):
    from unittest.mock import MagicMock

    fake_user = {
        "id": "user_rl_test",
        "email": "ok@example.com",
        "password_hash": "",
        "is_active": True,
    }
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.set.return_value = None

    headers = {"x-forwarded-for": "66.66.66.66"}
    payload = {"email": "ok@example.com", "password": "goodpassword1"}

    with (
        patch("src.services.auth_service.db_users.get_user_by_email", return_value=fake_user),
        patch("src.services.auth_service.verify_password", return_value=True),
        patch("src.db.sessions.db", mock_db),
    ):
        resp = await client.post("/auth/login", json=payload, headers=headers)
    assert resp.status_code == 200
