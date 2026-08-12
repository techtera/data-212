from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status

from src.config import get_settings
from src.db.crud import query_docs

logger = logging.getLogger(__name__)


def check_job_quota(request: Request) -> None:
    """FastAPI dependency — enforce per-user daily job quota.

    Counts jobs in Firestore where owner_id == current user and
    created_at >= start of today (UTC).  Raises HTTP 429 if the count
    meets or exceeds MAX_JOBS_PER_USER_PER_DAY.

    Must be called BEFORE any Firestore write in POST /jobs.
    Quota checks happen after require_auth so request.state.user_id is set.

    Usage:
        router.post("/jobs", dependencies=[Depends(require_auth), Depends(check_job_quota)])
    """
    settings = get_settings()
    max_jobs = settings.max_jobs_per_user_per_day

    user_id: str = getattr(request.state, "user_id", "")
    if not user_id:
        # require_auth should have already rejected unauthenticated requests;
        # this is a belt-and-suspenders guard.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Start of today in UTC (midnight).
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        jobs_today = query_docs(
            "jobs",
            filters=[
                ("owner_id", "==", user_id),
                ("created_at", ">=", start_of_day.isoformat()),
            ],
            limit=max_jobs + 1,  # only need to know if count >= max; fetch one extra
        )
    except Exception:
        # DB error — fail open on quota (don't block the user for a transient error).
        logger.warning("Quota check failed — allowing request (details suppressed)")
        return

    if len(jobs_today) >= max_jobs:
        logger.info("Daily job quota reached for a user (user_id not logged)")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(f"Daily job limit of {max_jobs} reached. Please try again tomorrow."),
        )
