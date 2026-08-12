from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Set ALLOW_DEV_TOKEN before any src module is imported ─────────────────────
# V2 middleware checks this flag to allow the legacy "dev-token-change-me" token
# in tests. Must be set before src.config is imported so lru_cache picks it up.
os.environ.setdefault("ALLOW_DEV_TOKEN", "true")

# ── Firebase stub — must happen BEFORE any src.db module is imported ──────────
#
# firebase_admin is patched at the top of conftest so that when pytest collects
# test_crud.py / test_db_jobs.py and Python imports src.db.firebase, the real
# firebase_admin SDK (and any network call) is never executed.
#
# The patch is applied at module scope (not inside a fixture) so it takes effect
# during the collection phase, before the first test runs.

_mock_firebase_admin = MagicMock()
_mock_firebase_admin.get_app.side_effect = ValueError("no app")  # triggers initialize_app
_mock_firebase_admin.initialize_app.return_value = MagicMock()
_mock_credentials = MagicMock()
_mock_credentials.Certificate.return_value = MagicMock()
_mock_firebase_admin.credentials = _mock_credentials

_mock_firestore_module = MagicMock()
_mock_db_client = MagicMock()
_mock_firestore_module.client.return_value = _mock_db_client
_mock_firebase_admin.firestore = _mock_firestore_module

# Patch sys.modules so `import firebase_admin` anywhere returns our mock.
sys.modules["firebase_admin"] = _mock_firebase_admin
sys.modules["firebase_admin.credentials"] = _mock_credentials
sys.modules["firebase_admin.firestore"] = _mock_firestore_module

# Also make the credential file check pass by patching pathlib.Path.exists
# for the specific firebase init call.
_path_exists_patch = patch("pathlib.Path.exists", return_value=True)
_path_exists_patch.start()

# ── Standard fixtures ─────────────────────────────────────────────────────────

from src.config import Settings, get_settings  # noqa: E402
from src.main import app  # noqa: E402


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
    """Valid Authorization header using the configured ADMIN_TOKEN.

    Works because ALLOW_DEV_TOKEN=true is set at module scope above,
    so V2 middleware accepts the dev-token for tests.
    """
    return {"Authorization": f"Bearer {settings.admin_token}"}


@pytest.fixture
def bad_auth_headers() -> dict[str, str]:
    """An Authorization header carrying a deliberately wrong token."""
    return {"Authorization": "Bearer wrong-token-xyz"}
