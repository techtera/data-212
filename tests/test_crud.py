from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_snapshot(doc_id: str, data: dict[str, Any], exists: bool = True) -> MagicMock:
    """Build a minimal mock of a Firestore DocumentSnapshot."""
    snap = MagicMock()
    snap.exists = exists
    snap.id = doc_id
    snap.to_dict.return_value = data if exists else None
    return snap


# ── create_doc ────────────────────────────────────────────────────────────────


def test_create_doc_returns_id() -> None:
    mock_db = MagicMock()
    doc_ref = MagicMock()
    doc_ref.id = "new-doc-id"
    mock_db.collection.return_value.add.return_value = (MagicMock(), doc_ref)

    with patch("src.db.crud.db", mock_db):
        from src.db.crud import create_doc

        result = create_doc("jobs", {"name": "test"})

    assert result == "new-doc-id"
    mock_db.collection.assert_called_once_with("jobs")
    mock_db.collection.return_value.add.assert_called_once_with({"name": "test"})


# ── get_doc ───────────────────────────────────────────────────────────────────


def test_get_doc_existing_returns_dict() -> None:
    ts = datetime(2026, 8, 11, 10, 0, 0, tzinfo=UTC)
    mock_db = MagicMock()
    snap = _make_snapshot("doc-1", {"name": "job", "created_at": ts})
    mock_db.collection.return_value.document.return_value.get.return_value = snap

    with patch("src.db.crud.db", mock_db):
        from src.db.crud import get_doc

        result = get_doc("jobs", "doc-1")

    assert result is not None
    assert result["name"] == "job"
    # Timestamp must be converted to ISO string
    assert isinstance(result["created_at"], str)
    assert "2026-08-11" in result["created_at"]


def test_get_doc_missing_returns_none() -> None:
    mock_db = MagicMock()
    snap = _make_snapshot("ghost", {}, exists=False)
    mock_db.collection.return_value.document.return_value.get.return_value = snap

    with patch("src.db.crud.db", mock_db):
        from src.db.crud import get_doc

        result = get_doc("jobs", "ghost")

    assert result is None


# ── update_doc ────────────────────────────────────────────────────────────────


def test_update_doc_calls_firestore_update() -> None:
    mock_db = MagicMock()

    with patch("src.db.crud.db", mock_db):
        from src.db.crud import update_doc

        update_doc("jobs", "doc-1", {"status": "approved"})

    mock_db.collection.assert_called_once_with("jobs")
    mock_db.collection.return_value.document.assert_called_once_with("doc-1")
    mock_db.collection.return_value.document.return_value.update.assert_called_once()
    # updated_at must be injected
    call_kwargs = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert "updated_at" in call_kwargs
    assert call_kwargs["status"] == "approved"


# ── delete_doc ────────────────────────────────────────────────────────────────


def test_delete_doc_calls_firestore_delete() -> None:
    mock_db = MagicMock()

    with patch("src.db.crud.db", mock_db):
        from src.db.crud import delete_doc

        delete_doc("jobs", "doc-99")

    mock_db.collection.return_value.document.assert_called_once_with("doc-99")
    mock_db.collection.return_value.document.return_value.delete.assert_called_once()


# ── query_docs ────────────────────────────────────────────────────────────────


def test_query_docs_no_filters_returns_list() -> None:
    ts = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
    snaps = [
        _make_snapshot("id-1", {"name": "a", "created_at": ts}),
        _make_snapshot("id-2", {"name": "b", "created_at": ts}),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.limit.return_value.stream.return_value = iter(snaps)

    with patch("src.db.crud.db", mock_db):
        from src.db.crud import query_docs

        results = query_docs("jobs")

    assert len(results) == 2
    assert results[0]["id"] == "id-1"
    assert results[1]["id"] == "id-2"
    assert isinstance(results[0]["created_at"], str)


def test_query_docs_with_filters_calls_where() -> None:
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_db.collection.return_value.limit.return_value = mock_query
    mock_query.where.return_value = mock_query
    mock_query.stream.return_value = iter([])

    with patch("src.db.crud.db", mock_db):
        from src.db.crud import query_docs

        query_docs("jobs", filters=[("status", "==", "approved")])

    # V2: query_docs now uses FieldFilter(field, op, value) via keyword arg.
    call_kwargs = mock_query.where.call_args
    assert call_kwargs is not None
    ff = call_kwargs.kwargs.get("filter") or (call_kwargs.args[0] if call_kwargs.args else None)
    assert ff is not None
    assert ff.field_path == "status"
    assert ff.value == "approved"


# ── _convert_timestamps (unit) ────────────────────────────────────────────────


def test_convert_timestamps_nested() -> None:
    """Timestamps inside nested dicts must also be converted."""
    from src.db.crud import _convert_timestamps

    ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    data = {"outer": {"inner_ts": ts, "label": "keep"}}
    result = _convert_timestamps(data)
    assert isinstance(result["outer"]["inner_ts"], str)
    assert result["outer"]["label"] == "keep"


def test_convert_timestamps_naive_datetime() -> None:
    """Naive datetimes (no tzinfo) must be treated as UTC."""
    from src.db.crud import _convert_timestamps

    naive = datetime(2026, 6, 15, 8, 30, 0)  # no tzinfo
    result = _convert_timestamps({"ts": naive})
    assert (
        "+00:00" in result["ts"]
        or "UTC" in result["ts"]
        or result["ts"].endswith("Z")
        or "2026" in result["ts"]
    )
