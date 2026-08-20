"""Google Cloud Storage service for signed URL generation."""

import datetime

from google.cloud import storage
from google.oauth2 import service_account

from .config import settings

_client: storage.Client | None = None
_bucket: storage.Bucket | None = None


def _get_bucket() -> storage.Bucket:
    """Lazily initialize GCS client and return the bucket."""
    global _client, _bucket
    if _bucket is None:
        credentials = service_account.Credentials.from_service_account_file(
            settings.GCS_SA_KEY_PATH
        )
        _client = storage.Client(credentials=credentials, project=credentials.project_id)
        _bucket = _client.bucket(settings.GCS_BUCKET_NAME)
    return _bucket


def mint_signed_put_url(
    object_path: str, content_type: str = "application/zip"
) -> str:
    """Generate a V4 signed URL for uploading (PUT) an object."""
    bucket = _get_bucket()
    blob = bucket.blob(object_path)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=settings.GCS_SIGNED_URL_TTL),
        method="PUT",
        content_type=content_type,
    )
    return url


def mint_signed_get_url(object_path: str) -> str:
    """Generate a V4 signed URL for downloading (GET) an object."""
    bucket = _get_bucket()
    blob = bucket.blob(object_path)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=settings.GCS_SIGNED_URL_TTL),
        method="GET",
    )
    return url


def object_exists(object_path: str) -> bool:
    """Check whether an object exists in the bucket."""
    bucket = _get_bucket()
    blob = bucket.blob(object_path)
    return blob.exists()
