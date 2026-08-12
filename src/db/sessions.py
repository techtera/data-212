from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from src.config import get_settings
from src.db.crud import delete_doc, get_doc, query_docs
from src.db.firebase import db  # module-level import — same pattern as crud.py

logger = logging.getLogger(__name__)

COLLECTION = "sessions"


def _hash_token(raw_token: str) -> str:
    """Return the lowercase hex SHA-256 digest of *raw_token*.

    This is the value stored as the Firestore document ID.
    The raw token is NEVER stored or logged.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_session(user_id: str) -> str:
    """Generate a new session, persist its SHA-256 hash, and return the raw token ONCE.

    The raw token is returned to the caller exactly once and is never stored.
    Document ID = SHA-256(raw_token) as lowercase hex (64 chars).
    """
    settings = get_settings()
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=settings.session_ttl_hours)

    data: dict[str, Any] = {
        "user_id": user_id,
        "created_at": now,
        "expires_at": expires_at,
        "revoked": False,
    }

    # Use the hash as the document ID so lookup is O(1) — no query needed.
    db.collection(COLLECTION).document(token_hash).set(data)
    logger.info("Session created (token hash stored, raw token not logged)")
    return raw_token


def get_session_by_token_hash(token_hash: str) -> dict[str, Any] | None:
    """Fetch a session document by its token hash.

    Returns the session dict (with injected ``id`` = token_hash) or None.
    Does NOT check expiry — callers must verify ``expires_at`` themselves.
    """
    doc = get_doc(COLLECTION, token_hash)
    if doc is None:
        return None
    doc["id"] = token_hash
    return doc


def delete_session(token_hash: str) -> None:
    """Revoke a session by hard-deleting its Firestore document."""
    delete_doc(COLLECTION, token_hash)
    logger.info("Session deleted (token hash not logged)")


def delete_all_user_sessions(user_id: str) -> None:
    """Hard-delete every session document belonging to *user_id*.

    Used for security events (password change, force-logout-all).
    """
    rows = query_docs(
        COLLECTION,
        filters=[("user_id", "==", user_id)],
        limit=500,
    )
    batch = db.batch()
    for row in rows:
        ref = db.collection(COLLECTION).document(row["id"])
        batch.delete(ref)
    if rows:
        batch.commit()
        logger.info("Deleted %d session(s) for a user (user_id not logged)", len(rows))


def hash_token(raw_token: str) -> str:
    """Public re-export of the token hashing function for use in middleware."""
    return _hash_token(raw_token)
