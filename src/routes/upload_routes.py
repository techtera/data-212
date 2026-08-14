"""Upload routes — V4-GCS: real GCS signed PUT URLs.

POST /uploads/sign  →  mints a V4 signed PUT URL scoped to a single object in
the datasets/ prefix. The FE PUTs the zip file directly to GCS using this URL.

The old PUT /dev/upload/{id} no-op endpoint has been removed; the FE no longer
sends upload bytes to this backend.
"""

from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Depends

from src.middleware.auth import require_auth
from src.schemas.fe_contract import UploadSignResponse
from src.services.gcs_service import mint_signed_put_url

router = APIRouter(tags=["uploads"], dependencies=[Depends(require_auth)])


@router.post("/uploads/sign", response_model=UploadSignResponse)
async def sign_upload() -> UploadSignResponse:
    """Mint a short-lived GCS V4 signed PUT URL for a dataset upload.

    Returns:
        - signed_put_url: A time-boxed (≤15 min) GCS V4 signed PUT URL
          scoped to a single object: datasets/{dataset_id}/raw.zip
        - object_path: The GCS object path that the FE must pass back in
          POST /jobs to prove the upload happened.

    Security:
        - Content-type restricted to application/zip
        - TTL capped at 900 seconds
        - Scoped to datasets/ prefix only
        - Caller must be authenticated (require_auth dependency)
    """
    dataset_id = f"ds_{int(time.time() * 1000):x}_{secrets.token_hex(4)}"
    object_path = f"datasets/{dataset_id}/raw.zip"

    signed_put_url = mint_signed_put_url(
        object_path=object_path,
        content_type="application/zip",
    )

    return UploadSignResponse(signed_put_url=signed_put_url, object_path=object_path)
