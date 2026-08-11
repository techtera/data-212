from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import Settings, get_settings

# auto_error=False so we can return a clean 401 instead of FastAPI's default 403
_bearer = HTTPBearer(auto_error=False)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency — Phase 1 hardcoded Bearer token check.

    Compares the incoming Bearer value against ADMIN_TOKEN from the environment.
    Returns HTTP 401 if the token is absent or wrong.

    Usage:
        router = APIRouter(dependencies=[Depends(require_auth)])
    """
    token = credentials.credentials if credentials else None
    if token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
