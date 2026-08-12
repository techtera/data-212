from __future__ import annotations

import logging
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

from src.config import get_settings

logger = logging.getLogger(__name__)

# ── In-memory store ───────────────────────────────────────────────────────────
# Maps client_ip -> deque of timestamps (seconds since epoch) for recent attempts.
# Thread-safe via a single module-level lock (single-process deployment on Render).
_lock = threading.Lock()
_attempts: dict[str, deque[float]] = {}


def _client_ip(request: Request) -> str:
    """Extract the best-available client IP from the request.

    Checks X-Forwarded-For first (Render/Vercel proxy header), then falls
    back to the direct connection address.  Only the first (leftmost) address
    in X-Forwarded-For is used — this is the originating client IP.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_login_rate_limit(request: Request) -> None:
    """FastAPI dependency — enforce per-IP login rate limit.

    Raises HTTP 429 with a Retry-After header if the client IP has exceeded
    RATE_LIMIT_LOGIN_PER_MINUTE attempts in the last 60 seconds.

    Uses a sliding-window algorithm: timestamps older than 60 s are evicted on
    every call, keeping memory bounded even under sustained attack traffic.

    Usage:
        router.post("/auth/login", dependencies=[Depends(check_login_rate_limit)])
    """
    settings = get_settings()
    max_attempts = settings.rate_limit_login_per_minute
    window_seconds = 60.0

    ip = _client_ip(request)
    now = time.monotonic()

    with _lock:
        if ip not in _attempts:
            _attempts[ip] = deque()

        bucket = _attempts[ip]

        # Evict timestamps outside the sliding window.
        cutoff = now - window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= max_attempts:
            # Oldest timestamp tells us when the window next frees a slot.
            oldest = bucket[0]
            retry_after = int(window_seconds - (now - oldest)) + 1
            logger.warning("Rate limit exceeded for an IP (IP not logged)")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)


def reset_rate_limit(ip: str) -> None:
    """Clear the rate-limit bucket for *ip*.

    Used only in tests to reset state between test cases.
    NEVER expose this via an API route.
    """
    with _lock:
        _attempts.pop(ip, None)


def reset_all_rate_limits() -> None:
    """Clear every rate-limit bucket.

    Used only in tests.  NEVER expose via an API route.
    """
    with _lock:
        _attempts.clear()
