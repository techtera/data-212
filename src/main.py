from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
    logger.info("TERAFAC backend starting — Phase 1 (FE → BE → Firestore)")
    yield
    logger.info("TERAFAC backend shut down")


def create_app() -> FastAPI:
    """Application factory — returns a fully configured FastAPI instance."""
    app = FastAPI(
        title="TERAFAC Backend",
        description="Phase 1: FE → BE → Firestore with hardcoded auth and inline stubs.",
        version="0.1.0",
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
