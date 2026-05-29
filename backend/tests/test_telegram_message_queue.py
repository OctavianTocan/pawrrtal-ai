"""Tests for the per-chat FIFO turn dispatcher (#357)."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.channels.telegram.message_queue import (
    ChatMessageQueueDispatcher,
    QueuedTurn,
)


def _turn(*, chat_id: int, payload: object) -> QueuedTurn:
    return QueuedTurn(
        chat_id=chat_id,
        payload=payload,
        enqueued_at_monotonic=time.monotonic(),
    )


@pytest.mark.anyio
async def test_dispatcher_runs_turns_in_arrival_order() -> None:
    """Two messages on the same chat run FIFO, not concurrently (#357)."""
    completed: list[object] = []
    in_flight = 0
    max_in_flight = 0

    async def consumer(turn: QueuedTurn) -> None:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        try:
            # Short sleep simulates a turn doing real work; without
            # this the test couldn't observe concurrency violations.
            await asyncio.sleep(0.02)
            completed.append(turn.payload)
        finally:
            in_flight -= 1

    dispatcher = ChatMessageQueueDispatcher(consumer=consumer)
    await dispatcher.enqueue(_turn(chat_id=1, payload="first"))
    await dispatcher.enqueue(_turn(chat_id=1, payload="second"))
    await dispatcher.enqueue(_turn(chat_id=1, payload="third"))

    # Wait long enough for the worker to drain all three.
    for _ in range(50):
        if len(completed) == 3:
            break
        await asyncio.sleep(0.01)

    assert completed == ["first", "second", "third"], (
        "FIFO order violated — second message ran before first finished"
    )
    assert max_in_flight == 1, (
        f"Concurrency budget broken — saw {max_in_flight} turns running at once"
    )

    await dispatcher.shutdown()


@pytest.mark.anyio
async def test_separate_chats_run_independently() -> None:
    """Two different chats each get their own worker; one's queue doesn't block the other."""
    started: list[tuple[int, str]] = []

    async def consumer(turn: QueuedTurn) -> None:
        started.append((turn.chat_id, turn.payload))
        # Slow turn on chat 1 must not delay chat 2.
        if turn.chat_id == 1:
            await asyncio.sleep(0.05)

    dispatcher = ChatMessageQueueDispatcher(consumer=consumer)
    await dispatcher.enqueue(_turn(chat_id=1, payload="slow"))
    await dispatcher.enqueue(_turn(chat_id=2, payload="fast"))

    # Wait until chat 2 has at least started; chat 1's slow turn
    # should not have blocked chat 2.
    for _ in range(50):
        if any(chat_id == 2 for chat_id, _ in started):
            break
        await asyncio.sleep(0.01)

    chat_ids_started = [chat_id for chat_id, _ in started]
    assert 1 in chat_ids_started
    assert 2 in chat_ids_started

    await dispatcher.shutdown()


@pytest.mark.anyio
async def test_is_running_and_pending_count_track_state() -> None:
    """``is_running`` flips while a turn is in flight; ``pending_count`` reflects backlog."""
    gate = asyncio.Event()
    seen_running: list[bool] = []

    async def consumer(turn: QueuedTurn) -> None:
        seen_running.append(True)
        await gate.wait()

    dispatcher = ChatMessageQueueDispatcher(consumer=consumer)
    assert dispatcher.is_running(chat_id=1) is False
    assert dispatcher.pending_count(chat_id=1) == 0

    await dispatcher.enqueue(_turn(chat_id=1, payload="first"))
    await dispatcher.enqueue(_turn(chat_id=1, payload="second"))

    # Yield long enough for the worker to pop the first item and call
    # the consumer; the second stays behind in the queue.
    for _ in range(50):
        if dispatcher.is_running(chat_id=1):
            break
        await asyncio.sleep(0.01)
    assert dispatcher.is_running(chat_id=1) is True
    assert dispatcher.pending_count(chat_id=1) == 1

    gate.set()
    for _ in range(50):
        if not dispatcher.is_running(chat_id=1) and dispatcher.pending_count(chat_id=1) == 0:
            break
        await asyncio.sleep(0.01)
    assert dispatcher.is_running(chat_id=1) is False
    assert dispatcher.pending_count(chat_id=1) == 0
    assert seen_running == [True, True]

    await dispatcher.shutdown()


@pytest.mark.anyio
async def test_stop_chat_cancels_in_flight_and_drops_queue() -> None:
    """``/stop`` semantics: cancel the running turn and clear pending ones."""
    started: list[object] = []
    cancelled = asyncio.Event()

    async def consumer(turn: QueuedTurn) -> None:
        started.append(turn.payload)
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    dispatcher = ChatMessageQueueDispatcher(consumer=consumer)
    await dispatcher.enqueue(_turn(chat_id=1, payload="running"))
    await dispatcher.enqueue(_turn(chat_id=1, payload="queued-1"))
    await dispatcher.enqueue(_turn(chat_id=1, payload="queued-2"))

    # Wait until the first turn started.
    for _ in range(50):
        if started:
            break
        await asyncio.sleep(0.01)

    cancelled_anything = await dispatcher.stop_chat(chat_id=1)
    assert cancelled_anything is True

    # Wait for the cancel to propagate.
    await asyncio.wait_for(cancelled.wait(), timeout=1.0)
    assert started == ["running"], "Stop didn't drop queued turns"

    await dispatcher.shutdown()


@pytest.mark.anyio
async def test_stop_chat_returns_false_when_idle() -> None:
    """Nothing running, nothing queued → ``stop_chat`` reports ``False``."""

    async def consumer(turn: QueuedTurn) -> None:
        return None

    dispatcher = ChatMessageQueueDispatcher(consumer=consumer)
    assert await dispatcher.stop_chat(chat_id=99) is False
    await dispatcher.shutdown()


@pytest.mark.anyio
async def test_consumer_exception_does_not_kill_the_worker() -> None:
    """A failed turn must not stop the worker from running the next one."""
    seen: list[object] = []

    async def consumer(turn: QueuedTurn) -> None:
        seen.append(turn.payload)
        if turn.payload == "boom":
            raise RuntimeError("consumer exploded")

    dispatcher = ChatMessageQueueDispatcher(consumer=consumer)
    await dispatcher.enqueue(_turn(chat_id=1, payload="boom"))
    await dispatcher.enqueue(_turn(chat_id=1, payload="after"))

    for _ in range(50):
        if "after" in seen:
            break
        await asyncio.sleep(0.01)

    assert seen == ["boom", "after"]
    await dispatcher.shutdown()
