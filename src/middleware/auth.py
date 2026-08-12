from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import Settings, get_settings
from src.db import sessions as db_sessions
from src.db import users as db_users

logger = logging.getLogger(__name__)

# auto_error=False so we can return a clean 401 instead of FastAPI's default 403
_bearer = HTTPBearer(auto_error=False)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency — V2 real session lookup.

    Flow:
    1. Extract Bearer token from Authorization header.
    2. If ALLOW_DEV_TOKEN=true AND token == ADMIN_TOKEN: attach mock admin user
       and return (local dev only — never enabled in production).
    3. Hash the raw token with SHA-256.
    4. Look up the hash in Firestore sessions collection.
    5. Check session is not expired and not revoked.
    6. Load the user from the users collection.
    7. Attach user_id and user_email to request.state.
    8. Any failure → generic 401 (no detail that leaks internal state).

    Usage:
        router = APIRouter(dependencies=[Depends(require_auth)])
    """
    _UNAUTHORIZED = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    raw_token: str | None = credentials.credentials if credentials else None

    if not raw_token:
        raise _UNAUTHORIZED

    # ── Dev-token fallback (explicitly opt-in, default off) ───────────────────
    if settings.allow_dev_token and raw_token == settings.admin_token:
        request.state.user_id = "dev-admin"
        request.state.user_email = "dev@localhost"
        return

    # ── Real session lookup ───────────────────────────────────────────────────
    token_hash = _hash(raw_token)

    try:
        session = db_sessions.get_session_by_token_hash(token_hash)
    except Exception:
        # Any unexpected DB error → 401, no internal details surfaced.
        logger.warning("Session lookup failed (details suppressed)")
        raise _UNAUTHORIZED from None

    if session is None:
        raise _UNAUTHORIZED

    # Check revoked flag
    if session.get("revoked", False):
        raise _UNAUTHORIZED

    # Check expiry — expires_at is either a datetime or an ISO string
    expires_at_raw = session.get("expires_at")
    try:
        if isinstance(expires_at_raw, str):
            expires_at = datetime.fromisoformat(expires_at_raw)
        elif isinstance(expires_at_raw, datetime):
            expires_at = expires_at_raw
        else:
            raise ValueError("unexpected expires_at type")

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if datetime.now(UTC) >= expires_at:
            raise _UNAUTHORIZED
    except HTTPException:
        raise
    except Exception:
        raise _UNAUTHORIZED from None

    # ── Load user ─────────────────────────────────────────────────────────────
    user_id: str = session.get("user_id", "")
    if not user_id:
        raise _UNAUTHORIZED

    try:
        user = db_users.get_user_by_id(user_id)
    except Exception:
        logger.warning("User lookup failed (details suppressed)")
        raise _UNAUTHORIZED from None

    if user is None or not user.get("is_active", False):
        raise _UNAUTHORIZED

    # Attach to request state for downstream use
    request.state.user_id = user_id
    request.state.user_email = user.get("email", "")
