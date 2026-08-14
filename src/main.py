from __future__ import annotations

import logging
import os
import subprocess
import sys
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
from src.services.broker import get_broker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("terafac")

# Research agent subprocess handle (module-level so lifespan can manage it)
_research_agent_proc: subprocess.Popen | None = None


def _start_research_agent() -> subprocess.Popen | None:
    """Auto-start the research agent container as a subprocess.

    Only starts if RESEARCH_AGENT_URL points to localhost (local dev).
    In production, the agent runs on Cloud Run and doesn't need local start.
    Returns the Popen handle or None if not needed / failed.
    """
    settings = get_settings()
    url = settings.research_agent_url

    # Only auto-start for localhost URLs
    if "localhost" not in url and "127.0.0.1" not in url:
        logger.info("Research agent URL is remote (%s) — not auto-starting", url)
        return None

    # Extract port from URL
    port = "9000"
    if ":" in url.split("//")[-1]:
        port = url.split(":")[-1].split("/")[0]

    # Find the agent script
    agent_script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cloud_run",
        "research_agent",
        "main.py",
    )
    if not os.path.exists(agent_script):
        logger.warning("Research agent script not found at %s — not auto-starting", agent_script)
        return None

    # Build env for the agent subprocess (inherit current env + set PORT)
    agent_env = {**os.environ, "PORT": port}

    python_exe = sys.executable
    logger.info("Auto-starting research agent on :%s (pid will follow)...", port)

    try:
        proc = subprocess.Popen(
            [python_exe, agent_script],
            env=agent_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.info("Research agent started (pid=%d) on :%s", proc.pid, port)
        return proc
    except Exception as e:
        logger.error("Failed to start research agent: %s", e)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _research_agent_proc

    # V3: Fail-closed — refuse to start without a properly configured JWT_HOP_SECRET
    settings = get_settings()
    if not settings.jwt_hop_secret or len(settings.jwt_hop_secret) < 32:
        raise RuntimeError("JWT_HOP_SECRET not configured or too short (min 32 chars)")

    # V4: Auto-start research agent container (local dev only)
    _research_agent_proc = _start_research_agent()

    # Give agent time to boot
    if _research_agent_proc:
        import asyncio

        await asyncio.sleep(2)

    # V3: Start the broker worker loop
    broker = get_broker()
    await broker.start_worker()
    logger.info("TERAFAC backend V4 ready (broker + research agent)")
    yield

    # Shutdown
    await broker.stop_worker()
    if _research_agent_proc:
        _research_agent_proc.terminate()
        try:
            _research_agent_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _research_agent_proc.kill()
        logger.info("Research agent stopped")
    logger.info("TERAFAC backend shut down")


def create_app() -> FastAPI:
    """Application factory — returns a fully configured FastAPI instance."""
    app = FastAPI(
        title="TERAFAC Backend",
        description="V4: Research agent with hop token security. Auto-starts agent container on localhost.",
        version="0.4.0",
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
