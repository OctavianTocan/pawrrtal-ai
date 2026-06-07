"""Regression: Codex thread-id persist survives streaming-task cancellation.

The ``codex_thread_created`` signal fires once per conversation (when the
Codex SDK creates the multi-turn thread). The runner used to persist
inline (``await persist_codex_thread_id(...)``) — strictly better than
fire-and-forget under normal completion, but a SIGTERM mid-stream still
cancelled every awaitable in the request task tree, dropping the UPDATE
before ``session.commit()`` could finish. The next turn would then start
a fresh Codex thread and the user would lose multi-turn context.

The fix detaches the persist into an ``asyncio.create_task`` tracked in
``_PENDING_CODEX_PERSIST_TASKS``. Cancellation of the streaming task no
longer cancels the persist task. ``await_pending_codex_persist_tasks``
is wired into ``main.lifespan``'s ``finally`` block so a graceful
SIGTERM drains the set before the event loop exits.
"""

from __future__ import annotations

import asyncio

import pytest

from app.channels import turn_orchestrator


@pytest.mark.anyio
async def test_register_codex_persist_task_tracks_and_releases_on_completion() -> None:
    """A registered task is tracked while running, released when it finishes."""
    started = asyncio.Event()
    finished = asyncio.Event()

    async def _slow() -> None:
        started.set()
        await asyncio.sleep(0.01)
        finished.set()

    task = asyncio.create_task(_slow())
    turn_orchestrator._register_codex_persist_task(task)
    assert task in turn_orchestrator._PENDING_CODEX_PERSIST_TASKS

    await started.wait()
    await task
    await finished.wait()
    # done_callback fires synchronously after completion; give the loop one tick
    await asyncio.sleep(0)
    assert task not in turn_orchestrator._PENDING_CODEX_PERSIST_TASKS


@pytest.mark.anyio
async def test_await_pending_codex_persist_tasks_drains_pending_set() -> None:
    """Shutdown drain blocks until every registered persist task finishes."""
    completed: list[int] = []

    async def _persist(label: int) -> None:
        await asyncio.sleep(0.02)
        completed.append(label)

    for label in (1, 2, 3):
        task = asyncio.create_task(_persist(label))
        turn_orchestrator._register_codex_persist_task(task)

    await turn_orchestrator.await_pending_codex_persist_tasks(timeout=2.0)

    # All three persists completed before the drain returned.
    assert sorted(completed) == [1, 2, 3]
    # The set is empty after drain.
    assert not turn_orchestrator._PENDING_CODEX_PERSIST_TASKS


@pytest.mark.anyio
async def test_await_pending_codex_persist_tasks_returns_immediately_when_empty() -> None:
    """Empty set short-circuits — no asyncio.gather call, no spurious sleep."""
    assert not turn_orchestrator._PENDING_CODEX_PERSIST_TASKS
    # If the implementation forgot the early-return guard, this would still
    # complete fast — but we time it loosely to detect any future regression
    # that introduces a per-call sleep.
    start = asyncio.get_event_loop().time()
    await turn_orchestrator.await_pending_codex_persist_tasks(timeout=5.0)
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 0.05


@pytest.mark.anyio
async def test_persist_task_survives_parent_task_cancellation() -> None:
    """Cancelling the spawning task does NOT cancel a registered persist task.

    Models the SIGTERM-mid-stream scenario: the streaming response task tree is
    cancelled, but the persist task — created via ``asyncio.create_task`` and
    tracked in ``_PENDING_CODEX_PERSIST_TASKS`` — runs to completion.
    """
    persist_done = asyncio.Event()

    async def _persist() -> None:
        # Use a fresh await so the surrounding task tree's cancellation can't
        # short-circuit us before the work happens.
        await asyncio.sleep(0.05)
        persist_done.set()

    persist_task: asyncio.Task[None] | None = None

    async def _spawn_and_be_cancelled() -> None:
        nonlocal persist_task
        persist_task = asyncio.create_task(_persist())
        turn_orchestrator._register_codex_persist_task(persist_task)
        # Yield so the persist task starts.
        await asyncio.sleep(0)
        # Now block forever — the test cancels us.
        await asyncio.sleep(10)

    parent = asyncio.create_task(_spawn_and_be_cancelled())
    # Give the parent a tick to spawn + register.
    await asyncio.sleep(0.005)
    parent.cancel()
    with pytest.raises(asyncio.CancelledError):
        await parent

    # The persist task should still complete on its own.
    assert persist_task is not None
    await asyncio.wait_for(persist_task, timeout=1.0)
    assert persist_done.is_set()
