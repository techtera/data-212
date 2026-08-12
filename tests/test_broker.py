"""V3-M2: Unit tests for src/services/broker.py.

Covers:
    - BrokerTask model validation
    - enqueue returns a correctly-formatted task_id
    - worker processes a valid pre_masking task (stub called)
    - worker processes a valid training task (stub called)
    - worker rejects an invalid hop token (stub NOT called, worker stays alive)
    - multiple tasks enqueued sequentially all execute
    - broker start/stop lifecycle (start_worker / stop_worker)
    - set_broker / get_broker singleton replacement
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.services.broker import BaseBroker, BrokerTask, InMemoryBroker, get_broker, set_broker
from src.services.jwt_hop import issue_hop_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _drain(broker: InMemoryBroker, timeout: float = 2.0) -> None:
    """Wait for the broker's queue to be fully processed."""
    await asyncio.wait_for(broker._queue.join(), timeout=timeout)


# ---------------------------------------------------------------------------
# BrokerTask model
# ---------------------------------------------------------------------------


def test_broker_task_fields():
    task = BrokerTask(job_id="job_001", task_type="pre_masking", hop_token="tok")
    assert task.job_id == "job_001"
    assert task.task_type == "pre_masking"
    assert task.hop_token == "tok"
    assert task.payload == {}


def test_broker_task_with_payload():
    task = BrokerTask(
        job_id="job_002",
        task_type="training",
        hop_token="tok2",
        payload={"extra": "data"},
    )
    assert task.payload == {"extra": "data"}


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_returns_task_id():
    broker = InMemoryBroker()
    token = issue_hop_token("job_001", "pre_masking")
    task = BrokerTask(job_id="job_001", task_type="pre_masking", hop_token=token)
    task_id = await broker.enqueue(task)
    assert task_id == "task_job_001_pre_masking"


@pytest.mark.asyncio
async def test_enqueue_puts_task_on_queue():
    broker = InMemoryBroker()
    token = issue_hop_token("job_002", "training")
    task = BrokerTask(job_id="job_002", task_type="training", hop_token=token)
    await broker.enqueue(task)
    assert broker._queue.qsize() == 1


# ---------------------------------------------------------------------------
# Worker — valid tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_calls_pre_masking_stub():
    """Worker must call run_pre_masking when task_type='pre_masking' and token is valid."""
    broker = InMemoryBroker()

    mock_pre = AsyncMock()
    mock_train = AsyncMock()

    with (
        patch("src.services.stubs.run_pre_masking", mock_pre),
        patch("src.services.stubs.run_training", mock_train),
    ):
        await broker.start_worker()
        token = issue_hop_token("job_pm", "pre_masking")
        task = BrokerTask(job_id="job_pm", task_type="pre_masking", hop_token=token)
        await broker.enqueue(task)
        await _drain(broker)
        await broker.stop_worker()

    mock_pre.assert_awaited_once_with("job_pm")
    mock_train.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_calls_training_stub():
    """Worker must call run_training when task_type='training' and token is valid."""
    broker = InMemoryBroker()

    mock_pre = AsyncMock()
    mock_train = AsyncMock()

    with (
        patch("src.services.stubs.run_pre_masking", mock_pre),
        patch("src.services.stubs.run_training", mock_train),
    ):
        await broker.start_worker()
        token = issue_hop_token("job_tr", "training")
        task = BrokerTask(job_id="job_tr", task_type="training", hop_token=token)
        await broker.enqueue(task)
        await _drain(broker)
        await broker.stop_worker()

    mock_train.assert_awaited_once_with("job_tr")
    mock_pre.assert_not_awaited()


# ---------------------------------------------------------------------------
# Worker — invalid token (stub must NOT be called; worker must stay alive)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_rejects_invalid_token_and_survives():
    """Worker must suppress the 401 from a bad token and keep running."""
    broker = InMemoryBroker()

    mock_pre = AsyncMock()
    mock_train = AsyncMock()

    with (
        patch("src.services.stubs.run_pre_masking", mock_pre),
        patch("src.services.stubs.run_training", mock_train),
    ):
        await broker.start_worker()

        # Enqueue a task with a deliberately bad token
        bad_task = BrokerTask(
            job_id="job_bad", task_type="pre_masking", hop_token="not.a.valid.jwt"
        )
        await broker.enqueue(bad_task)
        await _drain(broker)

        # Worker should still be alive — enqueue a valid task next
        good_token = issue_hop_token("job_good", "pre_masking")
        good_task = BrokerTask(job_id="job_good", task_type="pre_masking", hop_token=good_token)
        await broker.enqueue(good_task)
        await _drain(broker)

        await broker.stop_worker()

    # Bad task: stub never called; good task: stub called once
    mock_pre.assert_awaited_once_with("job_good")


# ---------------------------------------------------------------------------
# Worker — wrong-step token rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_rejects_wrong_step_token():
    """A training token presented on a pre_masking task must be rejected."""
    broker = InMemoryBroker()

    mock_pre = AsyncMock()

    with patch("src.services.stubs.run_pre_masking", mock_pre):
        await broker.start_worker()

        # Token is scoped to "training" but task_type is "pre_masking"
        wrong_token = issue_hop_token("job_ws", "training")
        task = BrokerTask(job_id="job_ws", task_type="pre_masking", hop_token=wrong_token)
        await broker.enqueue(task)
        await _drain(broker)
        await broker.stop_worker()

    mock_pre.assert_not_awaited()


# ---------------------------------------------------------------------------
# Multiple tasks processed sequentially
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_processes_multiple_tasks_sequentially():
    """All enqueued tasks should be processed in order."""
    broker = InMemoryBroker()
    call_order: list[str] = []

    async def fake_pre(job_id: str) -> None:
        call_order.append(f"pre:{job_id}")

    async def fake_train(job_id: str) -> None:
        call_order.append(f"train:{job_id}")

    with (
        patch("src.services.stubs.run_pre_masking", fake_pre),
        patch("src.services.stubs.run_training", fake_train),
    ):
        await broker.start_worker()

        for i in range(3):
            step = "pre_masking" if i % 2 == 0 else "training"
            token = issue_hop_token(f"job_{i}", step)
            await broker.enqueue(BrokerTask(job_id=f"job_{i}", task_type=step, hop_token=token))

        await _drain(broker)
        await broker.stop_worker()

    assert call_order == ["pre:job_0", "train:job_1", "pre:job_2"]


# ---------------------------------------------------------------------------
# Lifecycle: start / stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broker_start_creates_worker_task():
    broker = InMemoryBroker()
    assert broker._worker_task is None
    await broker.start_worker()
    assert broker._worker_task is not None
    await broker.stop_worker()


@pytest.mark.asyncio
async def test_broker_stop_cancels_worker_task():
    broker = InMemoryBroker()
    await broker.start_worker()
    worker_ref = broker._worker_task
    await broker.stop_worker()
    assert broker._worker_task is None
    assert worker_ref.done()


@pytest.mark.asyncio
async def test_broker_stop_is_idempotent():
    """stop_worker called twice must not raise."""
    broker = InMemoryBroker()
    await broker.start_worker()
    await broker.stop_worker()
    await broker.stop_worker()  # second call — must be a no-op


# ---------------------------------------------------------------------------
# Singleton: get_broker / set_broker
# ---------------------------------------------------------------------------


def test_get_broker_returns_base_broker_instance():
    broker = get_broker()
    assert isinstance(broker, BaseBroker)


def test_set_broker_replaces_singleton():
    original = get_broker()
    replacement = InMemoryBroker()
    set_broker(replacement)
    assert get_broker() is replacement
    # Restore for other tests
    set_broker(original)


def test_get_broker_returns_same_instance_twice():
    b1 = get_broker()
    b2 = get_broker()
    assert b1 is b2
