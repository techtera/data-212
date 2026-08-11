from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import TYPE_CHECKING

from src.config import get_settings

if TYPE_CHECKING:
    from google.cloud.firestore import Client


@lru_cache(maxsize=1)
def get_db() -> Client:
    """Return the shared Firestore client (lazy singleton, cached for the process lifetime).

    The client is constructed on first call and reused on every subsequent call.
    Credentials are resolved via:
      1. GOOGLE_APPLICATION_CREDENTIALS env var (path to a service-account JSON)
      2. Application Default Credentials  (gcloud auth application-default login)
    """
    from google.cloud import firestore  # type: ignore[import-untyped]

    settings = get_settings()
    return firestore.Client(project=settings.firestore_project_id)


@contextmanager
def db_context() -> Iterator[Client]:
    """Context manager that yields the shared Firestore client.

    Useful in tests or one-off scripts where you want an explicit scope.
    """
    yield get_db()
