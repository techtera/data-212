"""V3: In-memory job broker.

Provides an asyncio.Queue-based broker that:
  1. Accepts BrokerTask items via enqueue().
  2. Runs a worker loop that verifies the hop token before executing each task.
  3. Calls the appropriate stub (run_pre_masking / run_training) after
     successful token verification.

Design notes:
  - BaseBroker ABC makes it straightforward to swap in a FirestoreBroker (V4).
  - get_broker() / set_broker() give routes a singleton DI handle; tests can
    inject a custom broker via set_broker() to avoid real asyncio task races.
  - NEVER log raw hop tokens — only job_id + task_type metadata is logged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel

from src.services.jwt_hop import verify_hop_token

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task model
# ---------------------------------------------------------------------------


class BrokerTask(BaseModel):
    job_id: str
    task_type: str  # "pre_masking" | "research" | "training"
    hop_token: str  # short-lived JWT issued by issue_hop_token
    payload: dict = {}  # type: ignore[type-arg]  # any extra context


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseBroker(ABC):
    @abstractmethod
    async def enqueue(self, task: BrokerTask) -> str:
        """Enqueue a task.  Returns a task_id string."""

    @abstractmethod
    async def start_worker(self) -> None:
        """Start the background processing loop."""

    @abstractmethod
    async def stop_worker(self) -> None:
        """Stop the background processing loop."""


# ---------------------------------------------------------------------------
# In-memory broker (dev / test)
# ---------------------------------------------------------------------------


class InMemoryBroker(BaseBroker):
    """Local dev broker backed by asyncio.Queue.

    Worker loop:
        dequeue → verify_hop_token → execute stub → task_done
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[BrokerTask] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None  # type: ignore[type-arg]

    async def enqueue(self, task: BrokerTask) -> str:
        await self._queue.put(task)
        task_id = f"task_{task.job_id}_{task.task_type}"
        logger.info(
            "Broker enqueued task_id=%s job_id=%s type=%s", task_id, task.job_id, task.task_type
        )
        return task_id

    async def start_worker(self) -> None:
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Broker worker started")

    async def stop_worker(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None
        logger.info("Broker worker stopped")

    async def _worker_loop(self) -> None:
        """Continuously dequeue, verify, and execute tasks."""
        # Import stubs here (not at module top) to keep the import cycle clean
        # and allow tests to monkeypatch stubs before the worker runs.
        from src.services import stubs
        from src.services.research_service import run_research

        while True:
            task = await self._queue.get()
            try:
                # Verify hop token — raises HTTPException(401) on failure
                verify_hop_token(task.hop_token, expected_step=task.task_type)

                if task.task_type == "pre_masking":
                    await stubs.run_pre_masking(task.job_id)
                elif task.task_type == "research":
                    await run_research(task.job_id, task.hop_token)
                elif task.task_type == "training":
                    await stubs.run_training(task.job_id)
                else:
                    logger.warning("Broker: unknown task_type=%s — skipped", task.task_type)

                logger.info(
                    "Broker executed task_type=%s job_id=%s",
                    task.task_type,
                    task.job_id,
                )
            except Exception:
                # Suppress full details to avoid leaking hop-token content;
                # log only non-sensitive identifiers.
                logger.warning(
                    "Broker task failed job_id=%s task_type=%s (details suppressed)",
                    task.job_id,
                    task.task_type,
                )
            finally:
                self._queue.task_done()


# ---------------------------------------------------------------------------
# Singleton / DI helpers
# ---------------------------------------------------------------------------

_broker: BaseBroker | None = None


def get_broker() -> BaseBroker:
    """Return the singleton broker instance (creates InMemoryBroker on first call)."""
    global _broker
    if _broker is None:
        _broker = InMemoryBroker()
    return _broker


def set_broker(broker: BaseBroker) -> None:
    """Override the singleton broker — used in tests to inject a mock."""
    global _broker
    _broker = broker
