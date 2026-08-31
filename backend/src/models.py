"""Models registry - serves available models from models.json."""

import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import require_auth
from .db import fetch_all
from .gcs import mint_signed_get_url

router = APIRouter(prefix="/models", tags=["models"])

MODELS_FILE = Path(__file__).resolve().parent.parent / "models.json"


class ModelEntry(BaseModel):
    model_name: str
    category: str
    load_path: str
    inference_script: str
    finetune_script: str
    save_path: str
    user_id: str
    is_agent: bool = False


def _load_models() -> list[dict]:
    with open(MODELS_FILE, "r") as f:
        return json.load(f)


def get_model_by_name(model_name: str) -> dict | None:
    for m in _load_models():
        if m["model_name"] == model_name:
            return m
    return None


async def get_model_by_name_async(model_name: str, user_id: str = "") -> dict | None:
    """Check models.json first, then user_models DB table."""
    result = get_model_by_name(model_name)
    if result:
        return result
    if user_id:
        from .db import fetch_one as _fetch_one
        um = await _fetch_one(
            "SELECT * FROM user_models WHERE model_name = $1 AND user_id = $2",
            model_name, UUID(user_id),
        )
        if um:
            base_model_info = get_model_by_name(um["base_model"])
            is_agent = um["base_model"] == "agent-generated"
            train_script_gcs = f"gs://terafac-datasets/{um['inference_script']}" if um["inference_script"] else ""
            infer_script_gcs = train_script_gcs.replace("/train.py", "/inference.py") if train_script_gcs else ""
            return {
                "model_name": um["model_name"],
                "category": um["category"],
                "load_path": f"gs://terafac-datasets/{um['checkpoint_path']}" if um["checkpoint_path"] else "",
                "inference_script": infer_script_gcs if is_agent else (base_model_info["inference_script"] if base_model_info else ""),
                "finetune_script": train_script_gcs if is_agent else "",
                "usr_inference_script": infer_script_gcs if is_agent else train_script_gcs,
                "training_script": train_script_gcs if is_agent else "",
                "save_path": "",
                "user_id": str(um["user_id"]),
            }
    return None


@router.get("", response_model=list[ModelEntry])
async def list_models(user_id: UUID = Depends(require_auth)):
    """List models available to the current user (pretrained + user's finetuned)."""
    all_models = _load_models()
    visible = [
        m for m in all_models
        if m["user_id"] == "" or m["user_id"] == str(user_id)
    ]

    user_models = await fetch_all(
        "SELECT * FROM user_models WHERE user_id = $1 ORDER BY created_at DESC", user_id
    )
    for um in user_models:
        is_agent = um["base_model"] == "agent-generated"
        visible.append({
            "model_name": um["model_name"],
            "category": um["category"],
            "load_path": um["checkpoint_path"],
            "inference_script": um["inference_script"],
            "finetune_script": f"gs://terafac-datasets/{um['inference_script']}" if is_agent else "",
            "usr_inference_script": um["inference_script"],
            "is_agent": is_agent,
            "save_path": "",
            "user_id": str(um["user_id"]),
        })

    return visible


VIZ_IMAGES: dict[str, dict] = {
    "YOLO11L-MASKING-MODEL": {
        "inputs": ["visualization/YOLO11L-MASKING-MODEL/input_00e301cb-1784708951336000000_1.png", "visualization/YOLO11L-MASKING-MODEL/input_0a07478f-1785390020777458890_edge_42_mid.png"],
        "outputs": ["visualization/YOLO11L-MASKING-MODEL/output_pred_0000_00e301cb-1784708951336000000_1.png", "visualization/YOLO11L-MASKING-MODEL/output_pred_0001_0a07478f-1785390020777458890_edge_42_mid.png"],
    },
    "VGGT-SEGFORMER": {
        "inputs": ["visualization/VGGT-SEGFORMER/input_00e301cb-1784708951336000000_1.png", "visualization/VGGT-SEGFORMER/input_0a07478f-1785390020777458890_edge_42_mid.png"],
        "outputs": ["visualization/VGGT-SEGFORMER/output_pred_0000_00e301cb-1784708951336000000_1.png", "visualization/VGGT-SEGFORMER/output_pred_0001_0a07478f-1785390020777458890_edge_42_mid.png"],
    },
    "UNETPLUSPLUS-MODEL": {
        "inputs": ["visualization/UNETPLUSPLUS-MODEL/input_000cf964-1776404701334031000_aug00.png", "visualization/UNETPLUSPLUS-MODEL/input_000cf964-1776404701334031000_aug01.png"],
        "outputs": ["visualization/UNETPLUSPLUS-MODEL/output_pred_0000_000cf964-1776404701334031000_aug00.png", "visualization/UNETPLUSPLUS-MODEL/output_pred_0001_000cf964-1776404701334031000_aug01.png"],
    },
    "VGGT-UNETPP": {
        "inputs": ["visualization/VGGT-UNETPP/input_000cf964-1776404701334031000_aug00.png", "visualization/VGGT-UNETPP/input_000cf964-1776404701334031000_aug01.png"],
        "outputs": ["visualization/VGGT-UNETPP/output_pred_0000_000cf964-1776404701334031000_aug00.png", "visualization/VGGT-UNETPP/output_pred_0001_000cf964-1776404701334031000_aug01.png"],
    },
}


@router.get("/{model_name}/viz")
async def get_model_viz(model_name: str, user_id: UUID = Depends(require_auth)):
    """Get signed URLs for model sample visualization images."""
    viz = VIZ_IMAGES.get(model_name, {})
    if not viz:
        return {"inputs": [], "outputs": []}
    return {
        "inputs": [mint_signed_get_url(p) for p in viz["inputs"]],
        "outputs": [mint_signed_get_url(p) for p in viz["outputs"]],
    }
