from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.config import Settings, get_settings
from src.middleware.auth import require_auth
from src.middleware.rate_limit import check_login_rate_limit
from src.schemas.fe_contract import LoginRequest, LoginResponse

router = APIRouter(tags=["auth"])

# Far-future expiry for the V1 static token — never actually expires.
_STATIC_EXPIRES_AT = "2099-12-31T23:59:59Z"


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    dependencies=[Depends(check_login_rate_limit)],
)
async def login(
    req: LoginRequest,
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Validate credentials and return the static ADMIN_TOKEN.

    V1: compares against ADMIN_USERNAME / ADMIN_PASSWORD env vars.
    V2: replaced with bcrypt hash check + Firestore session creation.
    No Bearer token required — this IS the token-issuing endpoint.
    Rate-limited by IP via check_login_rate_limit dependency.
    """
    if req.username != settings.admin_username or req.password != settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return LoginResponse(token=settings.admin_token, expires_at=_STATIC_EXPIRES_AT)


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_auth)],
)
async def logout(response: Response) -> None:
    """Invalidate the current session.

    V1 no-op — the static token has no server-side state to revoke.
    V2: sets revoked=True on the Firestore session document.
    """
    return None
