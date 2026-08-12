"""V3: Firestore audit log for hop token events.

Records every token mint and verification to the `audit_log` collection so
the full chain from job creation to trained model is reconstructable.

Security rules:
- NEVER include the raw token string in any audit entry.
- Only metadata is written: event type, job_id, step, timestamps.
"""

from __future__ import annotations

import logging

from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore[import-untyped]

from src.db.crud import create_doc

logger = logging.getLogger(__name__)

COLLECTION = "audit_log"


def log_hop_issued(job_id: str, step: str, issued_at: int, expires_at: int) -> None:
    """Write a hop-token-issued event to the Firestore audit log.

    Called by issue_hop_token after minting.
    NEVER include the raw token string — only metadata is persisted.

    Args:
        job_id:     The job this token was issued for.
        step:       The task type the token is scoped to (e.g. "pre_masking").
        issued_at:  Unix timestamp when the token was minted (iat claim).
        expires_at: Unix timestamp when the token expires (exp claim).
    """
    try:
        create_doc(
            COLLECTION,
            {
                "event": "hop_token_issued",
                "job_id": job_id,
                "step": step,
                "issued_at": issued_at,
                "expires_at": expires_at,
                "ts": SERVER_TIMESTAMP,
            },
        )
        logger.debug("audit: hop_token_issued job_id=%s step=%s", job_id, step)
    except Exception:
        # Audit writes are best-effort — never crash the main flow.
        logger.warning("audit: failed to write hop_token_issued job_id=%s step=%s", job_id, step)


def log_hop_verified(job_id: str, step: str) -> None:
    """Write a hop-token-verified event to the Firestore audit log.

    Called by verify_hop_token after successful verification.
    NEVER include the raw token string.

    Args:
        job_id: The job the verified token was scoped to.
        step:   The task type the token was scoped to.
    """
    try:
        create_doc(
            COLLECTION,
            {
                "event": "hop_token_verified",
                "job_id": job_id,
                "step": step,
                "ts": SERVER_TIMESTAMP,
            },
        )
        logger.debug("audit: hop_token_verified job_id=%s step=%s", job_id, step)
    except Exception:
        # Audit writes are best-effort — never crash the main flow.
        logger.warning("audit: failed to write hop_token_verified job_id=%s step=%s", job_id, step)
