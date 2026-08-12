from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.db.crud import create_doc, get_doc, query_docs

logger = logging.getLogger(__name__)

COLLECTION = "users"


def create_user(
    email: str,
    password_hash: str,
    display_name: str,
) -> str:
    """Persist a new user document and return the generated user_id.

    Password is accepted as an already-hashed string — NEVER plain-text.
    The email is stored lowercase.
    """
    data: dict[str, Any] = {
        "email": email.lower(),
        "password_hash": password_hash,
        "display_name": display_name,
        "is_active": True,
        "created_at": datetime.now(UTC),
    }
    user_id = create_doc(COLLECTION, data)
    logger.info("Created user document (id hidden for security)")
    return user_id


def get_user_by_email(email: str) -> dict[str, Any] | None:
    """Look up a user by email (case-insensitive).

    Returns the user dict with an injected ``id`` field, or None.
    """
    rows = query_docs(
        COLLECTION,
        filters=[("email", "==", email.lower())],
        limit=1,
    )
    if not rows:
        return None
    return rows[0]


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    """Fetch a user document by its Firestore document ID.

    Returns the user dict with an injected ``id`` field, or None.
    """
    doc = get_doc(COLLECTION, user_id)
    if doc is None:
        return None
    doc["id"] = user_id
    return doc
