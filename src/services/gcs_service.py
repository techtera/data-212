"""GCS Service — signed URL minting and object existence checks.

Security rules enforced here:
- Signed URLs are scoped to a single object path (never wildcards/prefix-level).
- TTL is capped at 900 seconds (15 minutes).
- PUT URLs are restricted to a specific content-type.
- The SA key file is loaded by the SDK only — never read/logged by our code.
- No project-level IAM role; SA has bucket-level roles/storage.objectAdmin only.
"""

from __future__ import annotations

import datetime
import logging
from functools import lru_cache
from pathlib import Path

from google.cloud import storage

from src.config import get_settings

logger = logging.getLogger(__name__)

# Maximum TTL enforced regardless of config (security ceiling)
_MAX_TTL_SECONDS = 900

# Allowed prefixes — signed URLs can only target these paths
_ALLOWED_PREFIXES = ("datasets/", "weights/", "results/")


class GCSServiceError(Exception):
    """Raised when a GCS operation fails."""


def _get_storage_client() -> storage.Client:
    """Create a storage client using the SA key file.

    The SDK reads the JSON key internally — we never open or parse it ourselves.
    """
    settings = get_settings()
    key_path = Path(settings.gcs_sa_key_path)
    if not key_path.exists():
        raise GCSServiceError(
            f"GCS SA key file not found at '{settings.gcs_sa_key_path}'. "
            "Ensure GCS_SA_KEY_PATH is set correctly in .env."
        )
    return storage.Client.from_service_account_json(str(key_path))


@lru_cache
def _get_cached_client() -> storage.Client:
    """Cached storage client — instantiated once per process."""
    return _get_storage_client()


def _get_bucket() -> storage.Bucket:
    """Get the configured bucket object."""
    settings = get_settings()
    client = _get_cached_client()
    return client.bucket(settings.gcs_bucket_name)


def _validate_object_path(object_path: str) -> None:
    """Validate that the object path is within allowed prefixes.

    Prevents path traversal or access to objects outside the expected structure.
    """
    if not object_path:
        raise GCSServiceError("object_path cannot be empty")

    if not any(object_path.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        raise GCSServiceError(
            f"object_path must start with one of {_ALLOWED_PREFIXES}, got: '{object_path}'"
        )

    # Block path traversal attempts
    if ".." in object_path or "//" in object_path:
        raise GCSServiceError(f"Invalid object_path (path traversal detected): '{object_path}'")


def _clamp_ttl(ttl_seconds: int | None = None) -> int:
    """Clamp TTL to the configured max or 900s ceiling, whichever is lower."""
    settings = get_settings()
    if ttl_seconds is None:
        ttl_seconds = settings.gcs_signed_url_ttl_seconds
    # Enforce hard ceiling
    return min(ttl_seconds, _MAX_TTL_SECONDS, settings.gcs_signed_url_ttl_seconds)


def mint_signed_put_url(
    object_path: str,
    content_type: str = "application/zip",
    ttl_seconds: int | None = None,
) -> str:
    """Mint a V4 signed PUT URL for uploading an object to GCS.

    Args:
        object_path: The GCS object path (e.g. "datasets/ds_abc/raw.zip").
        content_type: Required content-type restriction on the upload.
        ttl_seconds: Override TTL (clamped to max 900s).

    Returns:
        A signed PUT URL string.

    Raises:
        GCSServiceError: If path validation fails or signing errors out.
    """
    _validate_object_path(object_path)
    ttl = _clamp_ttl(ttl_seconds)

    try:
        bucket = _get_bucket()
        blob = bucket.blob(object_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=ttl),
            method="PUT",
            content_type=content_type,
        )
        logger.info(
            "Minted signed PUT URL: path=%s, content_type=%s, ttl=%ds",
            object_path,
            content_type,
            ttl,
        )
        return url
    except Exception as exc:
        raise GCSServiceError(f"Failed to mint signed PUT URL for '{object_path}': {exc}") from exc


def mint_signed_get_url(
    object_path: str,
    ttl_seconds: int | None = None,
) -> str:
    """Mint a V4 signed GET URL for downloading an object from GCS.

    Args:
        object_path: The GCS object path (e.g. "results/job_123/best.pt").
        ttl_seconds: Override TTL (clamped to max 900s).

    Returns:
        A signed GET URL string.

    Raises:
        GCSServiceError: If path validation fails or signing errors out.
    """
    _validate_object_path(object_path)
    ttl = _clamp_ttl(ttl_seconds)

    try:
        bucket = _get_bucket()
        blob = bucket.blob(object_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=ttl),
            method="GET",
        )
        logger.info(
            "Minted signed GET URL: path=%s, ttl=%ds",
            object_path,
            ttl,
        )
        return url
    except Exception as exc:
        raise GCSServiceError(f"Failed to mint signed GET URL for '{object_path}': {exc}") from exc


def object_exists(object_path: str) -> bool:
    """Check whether an object exists in the GCS bucket.

    Args:
        object_path: The GCS object path to check.

    Returns:
        True if the object exists, False otherwise.

    Raises:
        GCSServiceError: If path validation fails or the API call errors.
    """
    _validate_object_path(object_path)

    try:
        bucket = _get_bucket()
        blob = bucket.blob(object_path)
        exists = blob.exists()
        logger.info("Object exists check: path=%s, exists=%s", object_path, exists)
        return exists
    except Exception as exc:
        raise GCSServiceError(f"Failed to check existence of '{object_path}': {exc}") from exc


def delete_object(object_path: str) -> bool:
    """Delete an object from the GCS bucket.

    Args:
        object_path: The GCS object path to delete.

    Returns:
        True if deleted successfully, False if object didn't exist.

    Raises:
        GCSServiceError: If path validation fails or the API call errors.
    """
    _validate_object_path(object_path)

    try:
        bucket = _get_bucket()
        blob = bucket.blob(object_path)
        if not blob.exists():
            return False
        blob.delete()
        logger.info("Deleted object: path=%s", object_path)
        return True
    except Exception as exc:
        raise GCSServiceError(f"Failed to delete '{object_path}': {exc}") from exc
