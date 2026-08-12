from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.db import users as db_users
from src.middleware.auth import require_auth
from src.middleware.rate_limit import check_login_rate_limit
from src.schemas.auth import SessionResponse, UserCreate, UserLogin, UserResponse
from src.services.auth_service import (
    authenticate_user,
    create_user_session,
    hash_password,
    invalidate_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── POST /auth/register ───────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_login_rate_limit)],
)
async def register(req: UserCreate) -> SessionResponse:
    """Register a new user, create a session, and return the raw token once.

    - 409 if email already in use.
    - Rate-limited by IP (shared limit with /auth/login).
    - Password is bcrypt-hashed before storage. Plain-text never persisted.
    - Raw token returned exactly once; only SHA-256 hash is stored.
    """
    # Check email uniqueness — same generic error regardless of reason.
    existing = db_users.get_user_by_email(req.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )

    password_hash = hash_password(req.password)
    user_id = db_users.create_user(
        email=req.email,
        password_hash=password_hash,
        display_name=req.display_name,
    )

    from src.config import get_settings

    settings = get_settings()
    raw_token = create_user_session(user_id)
    expires_in = settings.session_ttl_hours * 3600

    logger.info("New user registered (email and user_id not logged)")
    return SessionResponse(access_token=raw_token, expires_in=expires_in)


# ── POST /auth/login ──────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=SessionResponse,
    dependencies=[Depends(check_login_rate_limit)],
)
async def login(req: UserLogin) -> SessionResponse:
    """Authenticate with email + password and return a session token.

    - Rate-limited by IP.
    - 401 for both wrong password AND unknown email (no user enumeration).
    - Raw token returned exactly once.
    """
    user = authenticate_user(req.email, req.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = user.get("id", "")
    if not user_id:
        # Should never happen — guard against malformed Firestore docs.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from src.config import get_settings

    settings = get_settings()
    raw_token = create_user_session(user_id)
    expires_in = settings.session_ttl_hours * 3600

    return SessionResponse(access_token=raw_token, expires_in=expires_in)


# ── POST /auth/logout ─────────────────────────────────────────────────────────


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_auth)],
)
async def logout(
    request: Request,
    # Re-inject credentials so we can hash and delete the specific session.
    # require_auth already validated the token; we just need the raw value.
    credentials: str | None = None,
) -> None:
    """Invalidate the current session token.

    Deletes the SHA-256 hash from the Firestore sessions collection.
    The raw token is NEVER logged.
    """
    # Extract raw token from Authorization header.
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw_token = auth_header[7:]
        invalidate_session(raw_token)
    return None


# ── GET /auth/me ──────────────────────────────────────────────────────────────


@router.get(
    "/me",
    response_model=UserResponse,
    dependencies=[Depends(require_auth)],
)
async def me(request: Request) -> UserResponse:
    """Return the authenticated user's profile.

    Requires a valid Bearer session token.
    password_hash is NEVER included in the response.
    """
    user_id: str = getattr(request.state, "user_id", "")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db_users.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserResponse(
        id=user_id,
        email=user.get("email", ""),
        display_name=user.get("display_name", ""),
        created_at=user.get("created_at", ""),
    )
