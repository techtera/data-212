"""Admin routes — model management behind ADMIN_API_KEY."""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .config import settings
from .db import execute, fetch_all, fetch_one
from .gcs import mint_signed_put_url

router = APIRouter(prefix="/admin", tags=["admin"])


def _check_admin_key(x_admin_key: str = Header(...)):
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin not configured")
    if x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")


class SignRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=128)


class SignResponse(BaseModel):
    checkpoint_url: str
    inference_url: str
    finetune_url: str
    usr_inference_url: str
    gcs_paths: dict


class RegisterRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=128)
    category: str = Field(pattern=r"^(object_mask|edge_mask)$")
    load_path: str
    inference_script: str
    finetune_script: str
    usr_inference_script: str
    default_epochs: int = 10
    default_lr: float = 0.0001


class ModelResponse(BaseModel):
    model_name: str
    category: str
    load_path: str
    inference_script: str
    finetune_script: str
    usr_inference_script: str
    default_epochs: int
    default_lr: float


@router.post("/models/sign", response_model=SignResponse)
async def sign_model_uploads(body: SignRequest, x_admin_key: str = Header(...)):
    """Get signed PUT URLs for uploading model files to GCS."""
    _check_admin_key(x_admin_key)

    prefix = f"models/{body.model_name}"
    paths = {
        "checkpoint": f"{prefix}/checkpoint.pt",
        "inference": f"{prefix}/inference.py",
        "finetune": f"{prefix}/finetune.py",
        "usr_inference": f"{prefix}/usr_inference.py",
    }

    return SignResponse(
        checkpoint_url=mint_signed_put_url(paths["checkpoint"], content_type="application/octet-stream"),
        inference_url=mint_signed_put_url(paths["inference"], content_type="text/x-python"),
        finetune_url=mint_signed_put_url(paths["finetune"], content_type="text/x-python"),
        usr_inference_url=mint_signed_put_url(paths["usr_inference"], content_type="text/x-python"),
        gcs_paths=paths,
    )


@router.post("/models/register", response_model=ModelResponse)
async def register_model(body: RegisterRequest, x_admin_key: str = Header(...)):
    """Register a model in the platform after files are uploaded."""
    _check_admin_key(x_admin_key)

    existing = await fetch_one("SELECT id FROM platform_models WHERE model_name = $1", body.model_name)
    if existing:
        await execute(
            """UPDATE platform_models SET category=$1, load_path=$2, inference_script=$3,
               finetune_script=$4, usr_inference_script=$5, default_epochs=$6, default_lr=$7
               WHERE model_name=$8""",
            body.category, body.load_path, body.inference_script,
            body.finetune_script, body.usr_inference_script,
            body.default_epochs, body.default_lr, body.model_name,
        )
    else:
        await execute(
            """INSERT INTO platform_models (model_name, category, load_path, inference_script, finetune_script, usr_inference_script, default_epochs, default_lr)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            body.model_name, body.category, body.load_path, body.inference_script,
            body.finetune_script, body.usr_inference_script,
            body.default_epochs, body.default_lr,
        )

    return ModelResponse(
        model_name=body.model_name, category=body.category,
        load_path=body.load_path, inference_script=body.inference_script,
        finetune_script=body.finetune_script, usr_inference_script=body.usr_inference_script,
        default_epochs=body.default_epochs, default_lr=body.default_lr,
    )


@router.get("/models", response_model=list[ModelResponse])
async def list_admin_models(x_admin_key: str = Header(...)):
    """List all admin-registered platform models."""
    _check_admin_key(x_admin_key)
    rows = await fetch_all("SELECT * FROM platform_models ORDER BY created_at DESC")
    return [
        ModelResponse(
            model_name=r["model_name"], category=r["category"],
            load_path=r["load_path"], inference_script=r["inference_script"],
            finetune_script=r["finetune_script"], usr_inference_script=r["usr_inference_script"],
            default_epochs=r["default_epochs"], default_lr=r["default_lr"],
        )
        for r in rows
    ]


@router.delete("/models/{model_name}")
async def delete_model(model_name: str, x_admin_key: str = Header(...)):
    """Remove a model from the platform."""
    _check_admin_key(x_admin_key)
    result = await execute("DELETE FROM platform_models WHERE model_name = $1", model_name)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Model not found")
    return {"message": f"Model '{model_name}' deleted"}
