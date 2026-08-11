from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from src.middleware.auth import require_auth
from src.schemas.fe_contract import UploadSignResponse

router = APIRouter(tags=["uploads"], dependencies=[Depends(require_auth)])


@router.post("/uploads/sign", response_model=UploadSignResponse)
async def sign_upload() -> UploadSignResponse:
    """Mint a short-lived signed PUT URL for a dataset upload.

    V1 stub: returns a local echo path — no real GCS bucket exists yet.
    The FE PUTs the zip to the returned URL, then passes object_path to
    POST /jobs.  In V4 this mints a real GCS V4 signed URL.
    """
    dataset_id = f"ds_{int(time.time() * 1000):x}"
    object_path = f"datasets/{dataset_id}/raw.zip"
    # V1: signed_put_url points nowhere real; FE mock PUT succeeds trivially.
    signed_put_url = f"/dev/null/{dataset_id}"
    return UploadSignResponse(signed_put_url=signed_put_url, object_path=object_path)
