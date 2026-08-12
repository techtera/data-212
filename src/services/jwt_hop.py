"""V3: JWT hop token service.

Issues and verifies short-lived, single-purpose JWTs used by the broker
to authorise each downstream task hop (pre_masking, training, etc.).

Security rules (from backendplan.md V3 non-negotiables):
- Signing key loaded from config only — never hardcoded.
- Raw JWT strings are NEVER logged; only metadata (job_id, step, timestamps).
- Hop tokens are single-purpose: aud + step claim restrict what they can do.
- Expired or wrong-step tokens are rejected with HTTP 401.
"""

from __future__ import annotations

import logging
import time

import jwt
from fastapi import HTTPException, status

from src.config import get_settings
from src.services.audit import log_hop_issued, log_hop_verified

logger = logging.getLogger(__name__)


def issue_hop_token(job_id: str, step: str) -> str:
    """Mint a short-lived JWT for a single broker hop.

    Claims:
        sub  — job_id
        step — task type (e.g. "pre_masking", "training")
        iat  — issued-at (Unix timestamp)
        exp  — expiry  (iat + jwt_hop_ttl_seconds)
        iss  — jwt_hop_issuer  ("terafac-api")
        aud  — jwt_hop_audience ("terafac-worker")

    Signed with HS256 using JWT_HOP_SECRET from config.
    NEVER log the raw token — only metadata is logged.

    Returns:
        Raw JWT string.
    """
    settings = get_settings()
    now = int(time.time())
    expires_at = now + settings.jwt_hop_ttl_seconds
    payload = {
        "sub": job_id,
        "step": step,
        "iat": now,
        "exp": expires_at,
        "iss": settings.jwt_hop_issuer,
        "aud": settings.jwt_hop_audience,
    }
    token = jwt.encode(payload, settings.jwt_hop_secret, algorithm="HS256")
    # Log metadata only — NEVER the raw token string
    logger.info(
        "hop_token_issued job_id=%s step=%s issued_at=%d expires_at=%d",
        job_id,
        step,
        now,
        expires_at,
    )
    # Write audit entry — metadata only, no raw token
    log_hop_issued(job_id, step, issued_at=now, expires_at=expires_at)
    return token


def verify_hop_token(token: str, expected_step: str) -> dict:
    """Verify a hop token and return its claims on success.

    Checks:
        - HS256 signature against JWT_HOP_SECRET
        - Token not expired (exp claim)
        - Correct issuer (iss claim)
        - Correct audience (aud claim)
        - step claim matches expected_step

    Args:
        token:         Raw JWT string.
        expected_step: The task type this token must be scoped to.

    Returns:
        Decoded payload dict on success.

    Raises:
        HTTPException(401) on any failure (expired, bad sig, wrong step,
        wrong issuer/audience).  NEVER log the raw token.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_hop_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_hop_issuer,
            audience=settings.jwt_hop_audience,
        )
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hop token expired",
        ) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid hop token",
        ) from err

    if payload.get("step") != expected_step:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hop token step mismatch",
        )

    # Log verified metadata only — NEVER the raw token
    logger.info(
        "hop_token_verified job_id=%s step=%s",
        payload.get("sub"),
        payload.get("step"),
    )
    # Write audit entry — metadata only, no raw token
    log_hop_verified(payload.get("sub", ""), payload.get("step", ""))
    return payload
