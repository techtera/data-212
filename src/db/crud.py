from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore[import-untyped]
from google.cloud.firestore_v1.base_query import FieldFilter  # type: ignore[import-untyped]

# `db` is the only Firebase symbol ever used outside firebase.py.
# All other modules must import from here, not from firebase_admin directly.
from src.db.firebase import db

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _convert_timestamps(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert Firestore DatetimeWithNanoseconds / datetime values
    to ISO 8601 strings so returned dicts are JSON-serialisable.

    Only converts datetime instances; all other types are left untouched.
    """
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            # Normalise to UTC then emit ISO 8601 with timezone offset.
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            out[key] = value.isoformat()
        elif isinstance(value, dict):
            out[key] = _convert_timestamps(value)
        else:
            out[key] = value
    return out


# ── Public CRUD helpers ───────────────────────────────────────────────────────


def create_doc(collection: str, data: dict[str, Any]) -> str:
    """Write *data* as a new document in *collection*.

    Returns the Firestore-generated document ID.
    The caller should NOT include `id` in *data* — Firestore generates it.
    """
    _, doc_ref = db.collection(collection).add(data)
    logger.debug("Created document %s/%s", collection, doc_ref.id)
    return doc_ref.id


def get_doc(collection: str, doc_id: str) -> dict[str, Any] | None:
    """Fetch a single document by ID.

    Returns a dict (with timestamps converted to ISO strings) or None if the
    document does not exist.
    """
    snapshot = db.collection(collection).document(doc_id).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    return _convert_timestamps(data)


def update_doc(collection: str, doc_id: str, data: dict[str, Any]) -> None:
    """Merge *data* into an existing document (partial update).

    Always injects `updated_at = SERVER_TIMESTAMP` so the write timestamp is
    authoritative and consistent with the server clock.
    """
    payload = {**data, "updated_at": SERVER_TIMESTAMP}
    db.collection(collection).document(doc_id).update(payload)
    logger.debug("Updated document %s/%s", collection, doc_id)


def delete_doc(collection: str, doc_id: str) -> None:
    """Hard-delete a document. Silently succeeds if the document does not exist."""
    db.collection(collection).document(doc_id).delete()
    logger.debug("Deleted document %s/%s", collection, doc_id)


def query_docs(
    collection: str,
    filters: list[tuple[str, str, Any]] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return up to *limit* documents from *collection*, optionally filtered.

    Each *filter* tuple must be ``(field_path, op_string, value)`` where
    *op_string* is a Firestore operator such as ``"=="``, ``"<"``, ``">="``,
    ``"in"``, etc.

    Timestamps in returned dicts are converted to ISO 8601 strings.
    """
    query = db.collection(collection).limit(limit)
    if filters:
        for field, op, value in filters:
            query = query.where(filter=FieldFilter(field, op, value))

    results: list[dict[str, Any]] = []
    for snapshot in query.stream():
        data = snapshot.to_dict() or {}
        row = _convert_timestamps(data)
        row["id"] = snapshot.id  # always inject the doc id
        results.append(row)
    return results
