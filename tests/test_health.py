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


# ── Auth guard on registered /jobs route (M2+) ───────────────────────────────


async def test_jobs_route_no_token_returns_401(client: AsyncClient) -> None:
    """/jobs is now registered (M2) — missing token must return 401."""
    resp = await client.get("/jobs")
    assert resp.status_code == 401


async def test_jobs_route_wrong_token_returns_401(
    client: AsyncClient, bad_auth_headers: dict[str, str]
) -> None:
    """/jobs with a wrong token must return 401."""
    resp = await client.get("/jobs", headers=bad_auth_headers)
    assert resp.status_code == 401


async def test_jobs_route_correct_token_returns_200(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """With the correct token GET /jobs is admitted (200 — empty list is fine)."""
    from unittest.mock import patch

    with patch("src.routes.job_routes.job_service.list_jobs", return_value=[]):
        resp = await client.get("/jobs", headers=auth_headers)
    assert resp.status_code == 200


# ── Settings ──────────────────────────────────────────────────────────────────


def test_settings_defaults_loaded(settings) -> None:  # type: ignore[no-untyped-def]
    """Settings must load from .env and expose expected defaults."""
    assert settings.admin_token != ""
    assert settings.port == 8000
    assert len(settings.cors_origins_list) >= 1
