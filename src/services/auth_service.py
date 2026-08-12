from __future__ import annotations

import logging
from typing import Any

import bcrypt

from src.config import get_settings
from src.db import sessions as db_sessions
from src.db import users as db_users

logger = logging.getLogger(__name__)


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain* using the configured work factor.

    NEVER log or return the plain-text password.
    """
    settings = get_settings()
    rounds = settings.bcrypt_rounds
    salt = bcrypt.gensalt(rounds=rounds)
    hashed = bcrypt.hashpw(plain.encode(), salt)
    return hashed.decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the bcrypt *hashed* value, False otherwise.

    Uses a constant-time comparison internally — safe against timing attacks.
    NEVER log either argument.
    """
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        # Malformed hash or encoding error — treat as mismatch, no details surfaced.
        return False


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    """Look up a user by email and verify the password.

    Returns the user dict on success, or None on ANY failure.
    The failure reason is intentionally NOT distinguished (no user enumeration).
    NEVER log the email address or password.
    """
    user = db_users.get_user_by_email(email)
    if user is None:
        # Run a dummy verify to keep constant-time behaviour even when user missing.
        verify_password(password, "$2b$12$dummyhashfortiminguniformity000000000000000000000000000")
        return None

    if not user.get("is_active", False):
        verify_password(password, "$2b$12$dummyhashfortiminguniformity000000000000000000000000000")
        return None

    if not verify_password(password, user.get("password_hash", "")):
        return None

    return user


def create_user_session(user_id: str) -> str:
    """Create a new Firestore session for *user_id* and return the raw token ONCE.

    The raw token must be returned to the client immediately and is never stored.
    """
    return db_sessions.create_session(user_id)


def invalidate_session(raw_token: str) -> None:
    """Hash *raw_token* and delete the corresponding Firestore session document.

    Safe to call even if the session does not exist (no-op).
    NEVER log the raw token.
    """
    token_hash = db_sessions.hash_token(raw_token)
    db_sessions.delete_session(token_hash)
