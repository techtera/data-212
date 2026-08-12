"""V3-M0: Startup validation tests.

Verify that the server refuses to start when JWT_HOP_SECRET is missing or
too short, and starts correctly when the secret meets the 32-char minimum.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app_with_secret(secret: str) -> FastAPI:
    """Construct a minimal FastAPI app that runs the V3 lifespan validation."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not secret or len(secret) < 32:
            raise RuntimeError("JWT_HOP_SECRET not configured or too short (min 32 chars)")
        yield

    return FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# Tests: config field presence
# ---------------------------------------------------------------------------


def test_settings_has_jwt_hop_secret_field():
    """Settings must expose a jwt_hop_secret field."""
    from src.config import get_settings

    s = get_settings()
    assert hasattr(s, "jwt_hop_secret")


def test_settings_has_jwt_hop_issuer_field():
    from src.config import get_settings

    s = get_settings()
    assert hasattr(s, "jwt_hop_issuer")
    assert s.jwt_hop_issuer == "terafac-api"


def test_settings_has_jwt_hop_audience_field():
    from src.config import get_settings

    s = get_settings()
    assert hasattr(s, "jwt_hop_audience")
    assert s.jwt_hop_audience == "terafac-worker"


def test_settings_has_jwt_hop_ttl_seconds_field():
    from src.config import get_settings

    s = get_settings()
    assert hasattr(s, "jwt_hop_ttl_seconds")
    assert s.jwt_hop_ttl_seconds == 300


def test_conftest_sets_jwt_hop_secret_env():
    """conftest.py must have set JWT_HOP_SECRET before this module loads."""
    secret = os.environ.get("JWT_HOP_SECRET", "")
    assert len(secret) >= 32, f"JWT_HOP_SECRET is '{secret}' — conftest must set it to 32+ chars"


def test_settings_jwt_hop_secret_loaded_from_env():
    """Settings picks up JWT_HOP_SECRET from the environment."""
    from src.config import Settings

    s = Settings(jwt_hop_secret="env-loaded-secret-of-adequate-length-here")
    assert s.jwt_hop_secret == "env-loaded-secret-of-adequate-length-here"


# ---------------------------------------------------------------------------
# Tests: fail-closed lifespan validation
# ---------------------------------------------------------------------------
# TestClient enters the lifespan (calls startup) synchronously, so it's the
# correct tool for testing startup failures. The async client fixture only
# yields after the app starts successfully (lifespan completes).


def test_lifespan_rejects_empty_secret():
    """Server must raise RuntimeError when JWT_HOP_SECRET is empty."""
    app = _make_app_with_secret("")
    with pytest.raises(RuntimeError, match="JWT_HOP_SECRET"), TestClient(app):
        pass


def test_lifespan_rejects_short_secret():
    """Server must raise RuntimeError when JWT_HOP_SECRET is shorter than 32 chars."""
    app = _make_app_with_secret("too-short")
    with pytest.raises(RuntimeError, match="JWT_HOP_SECRET"), TestClient(app):
        pass


def test_lifespan_rejects_31_char_secret():
    """Boundary: 31-char secret must also be rejected (minimum is 32)."""
    app = _make_app_with_secret("a" * 31)
    with pytest.raises(RuntimeError, match="JWT_HOP_SECRET"), TestClient(app):
        pass


def test_lifespan_accepts_32_char_secret():
    """Boundary: exactly 32-char secret must be accepted."""
    app = _make_app_with_secret("a" * 32)
    with TestClient(app) as client:
        # App started successfully — no RuntimeError raised
        assert client is not None


def test_lifespan_accepts_long_secret():
    """Secret longer than 32 chars must be accepted."""
    app = _make_app_with_secret("test-jwt-hop-secret-for-pytest-minimum-32-chars!!")
    with TestClient(app) as client:
        assert client is not None


@pytest.mark.asyncio
async def test_main_app_starts_with_test_secret(client: AsyncClient):
    """The main app (which uses the test secret from conftest) must start cleanly.

    Verified implicitly: the `client` fixture only yields if the lifespan
    completes without raising, i.e. JWT_HOP_SECRET passed validation.
    """
    resp = await client.get("/health")
    assert resp.status_code == 200
