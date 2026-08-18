"""Authentication routes and the require_auth dependency."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from .config import settings
from .db import execute, fetch_one

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    display_name: str | None
    is_active: bool
    created_at: str


class TokenResponse(BaseModel):
    token: str
    expires_at: str
    user: UserResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS),
    ).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _hash_token(token: str) -> str:
    """SHA-256 hash a session token for storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _user_response(row) -> UserResponse:
    """Convert a DB row to a UserResponse."""
    return UserResponse(
        id=str(row["id"]),
        username=row["username"],
        email=row["email"],
        display_name=row["display_name"],
        is_active=row["is_active"],
        created_at=row["created_at"].isoformat(),
    )


# ---------------------------------------------------------------------------
# Dependency: require_auth
# ---------------------------------------------------------------------------


async def require_auth(request: Request) -> UUID:
    """Extract and validate the Bearer token. Returns user_id."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header[7:]  # strip "Bearer "
    token_hash = _hash_token(token)

    session = await fetch_one(
        """SELECT user_id, expires_at FROM sessions
           WHERE token_hash = $1""",
        token_hash,
    )

    if session is None:
        raise HTTPException(status_code=401, detail="Invalid session token")

    if session["expires_at"] < datetime.now(timezone.utc):
        # Clean up expired session
        await execute("DELETE FROM sessions WHERE token_hash = $1", token_hash)
        raise HTTPException(status_code=401, detail="Session expired")

    # Attach user_id to request state for convenience
    request.state.user_id = session["user_id"]
    return session["user_id"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest):
    """Register a new user."""
    # Check if username or email already exists
    existing = await fetch_one(
        "SELECT id FROM users WHERE username = $1 OR email = $2",
        body.username,
        body.email,
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already taken")

    password_hash = _hash_password(body.password)

    row = await fetch_one(
        """INSERT INTO users (username, email, password_hash, display_name)
           VALUES ($1, $2, $3, $4)
           RETURNING id, username, email, display_name, is_active, created_at""",
        body.username,
        body.email,
        password_hash,
        body.display_name,
    )

    return _user_response(row)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate with username + password, return session token."""
    user = await fetch_one(
        "SELECT id, username, email, display_name, is_active, password_hash, created_at FROM users WHERE username = $1",
        body.username,
    )

    if user is None or not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Generate session token
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_TTL_HOURS)

    await execute(
        """INSERT INTO sessions (user_id, token_hash, expires_at)
           VALUES ($1, $2, $3)""",
        user["id"],
        token_hash,
        expires_at,
    )

    return TokenResponse(
        token=token,
        expires_at=expires_at.isoformat(),
        user=_user_response(user),
    )


@router.post("/logout", status_code=204)
async def logout(request: Request, _user_id: UUID = Depends(require_auth)):
    """Invalidate the current session."""
    token = request.headers.get("Authorization", "")[7:]
    token_hash = _hash_token(token)
    await execute("DELETE FROM sessions WHERE token_hash = $1", token_hash)


@router.get("/me", response_model=UserResponse)
async def me(user_id: UUID = Depends(require_auth)):
    """Get current user's profile."""
    user = await fetch_one(
        "SELECT id, username, email, display_name, is_active, created_at FROM users WHERE id = $1",
        user_id,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_response(user)
