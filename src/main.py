from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import get_settings
from src.middleware.cors import apply_cors
from src.routes.auth_routes import router as auth_router
from src.routes.data_routes import router as data_router
from src.routes.health import router as health_router
from src.routes.job_action_routes import router as job_action_router
from src.routes.job_routes import router as job_router
from src.routes.upload_routes import router as upload_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("terafac")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # V3: Fail-closed — refuse to start without a properly configured JWT_HOP_SECRET
    settings = get_settings()
    if not settings.jwt_hop_secret or len(settings.jwt_hop_secret) < 32:
        raise RuntimeError("JWT_HOP_SECRET not configured or too short (min 32 chars)")
    logger.info("TERAFAC backend starting — V3 (broker + hop tokens)")
    yield
    logger.info("TERAFAC backend shut down")


def create_app() -> FastAPI:
    """Application factory — returns a fully configured FastAPI instance."""
    app = FastAPI(
        title="TERAFAC Backend",
        description="V3: Broker + JWT hop tokens. Session auth, bcrypt passwords, per-user quota, rate limiting.",
        version="0.3.0",
        lifespan=lifespan,
    )

    # ── Middleware ─────────────────────────────────────────────────────────────
    apply_cors(app)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(upload_router)
    app.include_router(job_router)
    app.include_router(job_action_router)
    app.include_router(data_router)
    return app


# Module-level instance consumed by uvicorn and the test client.
app = create_app()
