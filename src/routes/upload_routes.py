from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from src.middleware.auth import require_auth
from src.schemas.fe_contract import UploadSignResponse

router = APIRouter(tags=["uploads"], dependencies=[Depends(require_auth)])

_DEV_UPLOAD_PREFIX = "/dev/upload"


@router.post("/uploads/sign", response_model=UploadSignResponse)
async def sign_upload(request: Request) -> UploadSignResponse:
    """Mint a short-lived signed PUT URL for a dataset upload.

    V1 stub: the signed_put_url points to PUT /dev/upload/{id} on this same
    server — a no-op acceptor that lets the FE complete the two-hop upload
    dance without a real GCS bucket.

    In V4 this mints a real GCS V4 signed URL bound to the datasets/ prefix.
    """
    dataset_id = f"ds_{int(time.time() * 1000):x}"
    object_path = f"datasets/{dataset_id}/raw.zip"
    base = str(request.base_url).rstrip("/")
    signed_put_url = f"{base}{_DEV_UPLOAD_PREFIX}/{dataset_id}"
    return UploadSignResponse(signed_put_url=signed_put_url, object_path=object_path)


@router.put(
    "/dev/upload/{upload_id}",
    status_code=200,
    include_in_schema=False,  # hide from production Swagger docs
)
async def dev_upload_acceptor(upload_id: str) -> dict[str, str]:
    """V1-only no-op upload endpoint.

    The FE PUTs the raw zip bytes here after receiving the signed URL from
    POST /uploads/sign.  We discard the bytes; only the object_path (returned
    by /uploads/sign) is carried forward to POST /jobs.

    In V4 the FE PUTs directly to GCS — this endpoint is removed.
    """
    return {"ok": "accepted"}
