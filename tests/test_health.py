from __future__ import annotations

from httpx import AsyncClient

# ── /health ───────────────────────────────────────────────────────────────────


async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /health must return 200 with {status: ok} — no auth required."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_no_token_allowed(client: AsyncClient) -> None:
    """Health endpoint is reachable without any Authorization header."""
    resp = await client.get("/health")
    assert resp.status_code == 200


# ── Auth guard on future routes ───────────────────────────────────────────────


async def test_unregistered_route_no_token(client: AsyncClient) -> None:
    """/jobs is not yet registered in M0 — expect 404 (not 401).
    The auth guard only fires on routes that exist and declare the dependency.
    """
    resp = await client.get("/jobs")
    assert resp.status_code == 404


async def test_unregistered_route_wrong_token(
    client: AsyncClient, bad_auth_headers: dict[str, str]
) -> None:
    """Same as above with a wrong token — still 404 because route doesn't exist yet."""
    resp = await client.get("/jobs", headers=bad_auth_headers)
    assert resp.status_code == 404


async def test_unregistered_route_correct_token(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """With the correct token the server responds — 404 because route not yet wired."""
    resp = await client.get("/jobs", headers=auth_headers)
    assert resp.status_code == 404


# ── Settings ──────────────────────────────────────────────────────────────────


def test_settings_defaults_loaded(settings) -> None:  # type: ignore[no-untyped-def]
    """Settings must load from .env and expose expected defaults."""
    assert settings.admin_token != ""
    assert settings.port == 8000
    assert len(settings.cors_origins_list) >= 1
