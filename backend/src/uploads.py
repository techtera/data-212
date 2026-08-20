"""Upload signing route - generates signed PUT URLs for GCS."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from uuid import UUID

from .auth import require_auth
from .gcs import mint_signed_put_url

router = APIRouter(prefix="/uploads", tags=["uploads"])


class SignRequest(BaseModel):
    job_name: str = Field(min_length=1, max_length=128)


class SignResponse(BaseModel):
    job_name: str
    images_upload_url: str
    masks_upload_url: str


@router.post("/sign", response_model=SignResponse)
async def sign_upload_urls(body: SignRequest, user_id: UUID = Depends(require_auth)):
    """Generate signed PUT URLs for images.zip and masks.zip.
    Paths: upload/{job_name}/images.zip and upload/{job_name}/masks.zip"""
    job_name = body.job_name

    images_path = f"upload/{job_name}/images.zip"
    masks_path = f"upload/{job_name}/masks.zip"

    images_url = mint_signed_put_url(images_path, content_type="application/zip")
    masks_url = mint_signed_put_url(masks_path, content_type="application/zip")

    return SignResponse(
        job_name=job_name,
        images_upload_url=images_url,
        masks_upload_url=masks_url,
    )
