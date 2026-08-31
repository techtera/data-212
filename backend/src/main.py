"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import close_pool, init_pool
from .auth import router as auth_router
from .coding_training import router as coding_train_router
from .coding_inference import router as coding_inference_router
from .jobs import router as jobs_router
from .models import router as models_router
from .research import router as research_router
from .uploads import router as uploads_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB pool + tables on startup, close on shutdown."""
    logger.info("Initializing database pool...")
    await init_pool(settings.DATABASE_URL)
    logger.info("Database pool ready. Tables created.")
    yield
    logger.info("Shutting down database pool...")
    await close_pool()
    logger.info("Database pool closed.")


app = FastAPI(
    title="TERAFAC Fine-Tuning Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(coding_train_router)
app.include_router(coding_inference_router)
app.include_router(jobs_router)
app.include_router(models_router)
app.include_router(research_router)
app.include_router(uploads_router)


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "terafac-backend"}
