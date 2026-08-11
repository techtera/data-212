from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Settings, get_settings
from src.main import app


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTPX client wired directly to the FastAPI app (no network)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


@pytest.fixture
def auth_headers(settings: Settings) -> dict[str, str]:
    """Valid Authorization header using the configured ADMIN_TOKEN."""
    return {"Authorization": f"Bearer {settings.admin_token}"}


@pytest.fixture
def bad_auth_headers() -> dict[str, str]:
    """An Authorization header carrying a deliberately wrong token."""
    return {"Authorization": "Bearer wrong-token-xyz"}
