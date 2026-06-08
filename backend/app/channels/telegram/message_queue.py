"""Per-chat FIFO queue dispatcher for Telegram turn processing.

The Telegram bot currently cancels the in-flight stream when a new
user message arrives in the same chat — last-one-wins. That's fine
for the "user notices the model is going wrong and corrects mid-turn"
case but trashes the common case where the user fires off a
second message a second after the first ("oh, also: …"). The second
message clobbers the first and the first's reply is lost.

This module owns the FIFO replacement: every Telegram message hands
the bot a :class:`QueuedTurn` payload, which is appended to a
per-chat :class:`asyncio.Queue`. A single worker task per chat
drains the queue serially so each turn runs to completion before the
next one starts.

The dispatcher is framework-free; aiogram glue builds ``QueuedTurn``
payloads and calls :func:`enqueue` from :mod:`bot.py`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# How many seconds the worker waits for the next item before tearing
# itself down. Without this, an idle chat keeps a worker task alive
# forever (small but bounded leak). Workers re-spawn on demand when
# the next message arrives, so the user-visible behaviour is
# unchanged.
_WORKER_IDLE_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class QueuedTurn:
    """One pending turn for a single Telegram chat.

    ``payload`` is opaque to the dispatcher — the consumer (bot.py)
    decides what to put in it. Today it's the inbound aiogram
    ``Message`` object; future producers can wrap any shape the
    consumer recognises, such as a regenerate request.
    """

    chat_id: int
    payload: Any
    enqueued_at_monotonic: float


# A consumer is the async function the dispatcher invokes for each
# queued turn. It must run the turn to completion (or raise to surface
# the failure) before the next turn starts.
TurnConsumer = Callable[[QueuedTurn], Coroutine[Any, Any, None]]


@dataclass
class ChatMessageQueueDispatcher:
    """One worker task per chat, draining a FIFO queue of pending turns.

    Lifecycle:

    * :meth:`enqueue` appends to the per-chat queue and ensures a
      worker is running. Idempotent — calling it from any task is safe.
    * :meth:`stop_chat` cancels the in-flight turn AND drops queued
      items. Used by ``/stop``.
    * :meth:`shutdown` cancels every chat's worker — called from the
      bot's lifespan on shutdown.

    The dispatcher uses one consumer callable supplied at construction
    time so the worker doesn't have to fan out by message shape — the
    consumer is whatever ``bot.py`` wires up.
    """

    consumer: TurnConsumer
    """The callable invoked once per queued turn."""

    _queues: dict[int, asyncio.Queue[QueuedTurn]] = field(default_factory=dict)
    _workers: dict[int, asyncio.Task[None]] = field(default_factory=dict)
    _active_turns: dict[int, asyncio.Task[None]] = field(default_factory=dict)

    async def enqueue(self, turn: QueuedTurn) -> None:
        """Append ``turn`` to the chat's queue, spawning a worker on first use.

        Returns immediately; the turn runs in the background. The
        worker drains its queue serially so callers can rely on
        order-of-arrival being order-of-execution.
        """
        queue = self._queues.setdefault(turn.chat_id, asyncio.Queue())
        await queue.put(turn)
        if self._workers.get(turn.chat_id) is None or self._workers[turn.chat_id].done():
            self._workers[turn.chat_id] = asyncio.create_task(
                self._drain(turn.chat_id, queue),
                name=f"telegram-chat-worker-{turn.chat_id}",
            )

    def is_running(self, chat_id: int) -> bool:
        """Return whether a turn is currently in flight for ``chat_id``.

        Used by ``/status`` to decide between "running" and "idle".
        """
        task = self._active_turns.get(chat_id)
        return task is not None and not task.done()

    def pending_count(self, chat_id: int) -> int:
        """Return the number of turns sitting behind the in-flight one.

        Useful for the ``/status`` panel — if the user is wondering
        why their reply hasn't arrived, surfacing the backlog size
        gives them an honest answer.
        """
        queue = self._queues.get(chat_id)
        return queue.qsize() if queue is not None else 0

    async def stop_chat(self, chat_id: int) -> bool:
        """Cancel the in-flight turn and drop every queued turn for ``chat_id``.

            Returns ``True`` when something was actually cancelled,
            ``False`` when the chat had nothing running and nothing
        queued.
        """
        cancelled_anything = False

        active = self._active_turns.get(chat_id)
        if active is not None and not active.done():
            active.cancel()
            cancelled_anything = True

        queue = self._queues.get(chat_id)
        if queue is not None:
            while not queue.empty():
                queue.get_nowait()
                queue.task_done()
                cancelled_anything = True

        return cancelled_anything

    async def shutdown(self) -> None:
        """Cancel every worker — called from the bot's lifespan teardown."""
        for chat_id, worker in list(self._workers.items()):
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("CHAT_WORKER_SHUTDOWN_ERR chat_id=%s", chat_id)
        self._workers.clear()
        self._active_turns.clear()
        self._queues.clear()

    async def _drain(self, chat_id: int, queue: asyncio.Queue[QueuedTurn]) -> None:
        """Pop + run turns until the queue idles for the timeout window."""
        while True:
            try:
                turn = await asyncio.wait_for(
                    queue.get(),
                    timeout=_WORKER_IDLE_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.debug("CHAT_WORKER_IDLE_EXIT chat_id=%s", chat_id)
                return

            active = asyncio.create_task(self.consumer(turn), name=f"telegram-turn-{chat_id}")
            self._active_turns[chat_id] = active
            try:
                await active
            except asyncio.CancelledError:
                logger.info("CHAT_TURN_CANCELLED chat_id=%s", chat_id)
            except Exception:
                logger.exception("CHAT_TURN_ERR chat_id=%s", chat_id)
            finally:
                self._active_turns.pop(chat_id, None)
                queue.task_done()


__all__ = [
    "ChatMessageQueueDispatcher",
    "QueuedTurn",
    "TurnConsumer",
]
