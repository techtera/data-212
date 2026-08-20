"""Models registry - serves available models from models.json."""

import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import require_auth

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


def _load_models() -> list[dict]:
    with open(MODELS_FILE, "r") as f:
        return json.load(f)


def get_model_by_name(model_name: str) -> dict | None:
    for m in _load_models():
        if m["model_name"] == model_name:
            return m
    return None


@router.get("", response_model=list[ModelEntry])
async def list_models(user_id: UUID = Depends(require_auth)):
    """List models available to the current user (pretrained + user's finetuned)."""
    all_models = _load_models()
    visible = [
        m for m in all_models
        if m["user_id"] == "" or m["user_id"] == str(user_id)
    ]
    return visible
