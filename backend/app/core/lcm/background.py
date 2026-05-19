"""Fire-and-forget LCM compaction trigger.

Splits the background-task plumbing out of
``app.channels.turn_runner`` to keep that module under the project's
500-line file budget while keeping the public surface tiny:
``schedule_lcm_compaction`` is the single seam ``_finalize_turn``
calls when ``settings.lcm_enabled`` is on.

All errors are swallowed inside the bg helper — a failed compaction
is invisible to the user; the full message history stays preserved
in ``chat_messages``.

Concurrency model
-----------------
Compactions for the same conversation are serialized through a
per-conversation :class:`asyncio.Lock`.  Two consecutive turns (web +
Telegram, or rapid back-to-back user turns) would otherwise race each
other on:

* The shared ``(conversation_id, ordinal)`` unique constraint in
  ``lcm_context_items`` — both runs select the same eligible rows
  and try to insert a summary at the same freed ordinal slot.
* The DB connection pool — without a lock every concurrent turn
  pins a connection across the full LLM round-trip.

Different conversations stay parallel; only same-conversation runs
queue.  A reference count next to the lock tracks how many pending
+ in-flight tasks exist for the conversation; the lock entry drops
out of the registry only when the count reaches 0, so a waiter
suspended mid-``acquire`` is never separated from the live lock the
running holder is about to release.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.lcm import compact_leaf_if_needed
from app.db import async_session_maker

logger = logging.getLogger(__name__)

# Holds strong refs to fire-and-forget background tasks (LCM compaction).
# Without this set, the GC can collect the task mid-flight because
# ``asyncio.create_task`` only stores a weak reference to its return
# value; the task drops itself from this set on completion so the set
# doesn't grow unbounded.
_LCM_COMPACT_TASKS: set[asyncio.Task[None]] = set()


@dataclass
class _LockSlot:
    """One conversation's lock plus a refcount of pending + in-flight tasks.

    ``refcount`` is incremented in ``schedule_lcm_compaction`` (the
    synchronous half) and decremented in the task's ``finally``.  The
    slot is dropped from the registry only when the count returns to
    0 — i.e. when nothing is waiting on, holding, or about to acquire
    the lock.  This is the simplest correct way to avoid the
    "``Lock.release`` does not yield, so ``lock.locked()`` is always
    ``False`` in ``finally``" race that a naïve check has.
    """

    lock: asyncio.Lock
    refcount: int


# Per-conversation lock registry — serializes compaction passes for the
# same conversation across concurrent turns.  See module docstring for
# the concurrency model.
_LCM_COMPACT_LOCKS: dict[uuid.UUID, _LockSlot] = {}


def _claim_slot(conversation_id: uuid.UUID) -> _LockSlot:
    """Get or create the slot and synchronously bump its refcount.

    Centralised so both ``schedule_lcm_compaction`` (which claims the
    slot before launching a background task) and ``acquire_lcm_lock``
    (which claims it inside an async context manager) share the same
    "create-if-missing + refcount++" invariant — preventing drift if
    the refcount contract evolves.
    """
    slot = _LCM_COMPACT_LOCKS.get(conversation_id)
    if slot is None:
        slot = _LockSlot(lock=asyncio.Lock(), refcount=0)
        _LCM_COMPACT_LOCKS[conversation_id] = slot
    slot.refcount += 1
    return slot


def _release_slot(conversation_id: uuid.UUID) -> None:
    """Decrement the slot's refcount and drop it from the registry at zero."""
    slot = _LCM_COMPACT_LOCKS.get(conversation_id)
    if slot is None:
        return
    slot.refcount -= 1
    if slot.refcount <= 0:
        _LCM_COMPACT_LOCKS.pop(conversation_id, None)


@asynccontextmanager
async def acquire_lcm_lock(conversation_id: uuid.UUID) -> AsyncIterator[None]:
    """Hold the per-conversation lock for the duration of the ``with`` block.

    Public seam so foreground callers (the Telegram ``/compact`` command,
    one-off admin scripts) can run a compaction pass under the same
    lock the background helper uses. Without sharing the lock, a
    manual /compact firing concurrently with the auto-scheduled
    background pass would race on the ``(conversation_id, ordinal)``
    unique constraint.

    Same refcount + cleanup contract as
    :func:`schedule_lcm_compaction`: increment on entry, decrement in
    the ``finally``, drop the registry entry when the count returns
    to zero. The actual ``acquire`` happens inside the ``async with``
    so concurrent callers queue cleanly behind any current holder.
    """
    slot = _claim_slot(conversation_id)
    try:
        async with slot.lock:
            yield
    finally:
        _release_slot(conversation_id)


def schedule_lcm_compaction(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    model_id: str,
) -> None:
    """Fire one LCM leaf-compaction pass for ``conversation_id`` in the background.

    No-op when ``settings.lcm_enabled`` is ``False`` so callers can drop
    the gate.  The task keeps a strong reference in
    :data:`_LCM_COMPACT_TASKS` to survive GC and self-cleans on
    completion.

    The lock-slot refcount is bumped here — synchronously, before the
    task is created — so a waiter scheduled on top of an already-held
    lock cannot be orphaned by an in-flight ``finally`` block from a
    previous task that's already releasing the lock.
    """
    if not settings.lcm_enabled:
        return
    _claim_slot(conversation_id)
    task = asyncio.create_task(
        _lcm_compact_bg(
            conversation_id=conversation_id,
            user_id=user_id,
            model_id=model_id,
        )
    )
    _LCM_COMPACT_TASKS.add(task)
    task.add_done_callback(_LCM_COMPACT_TASKS.discard)


async def _lcm_compact_bg(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    model_id: str,
) -> None:
    """Run one LCM leaf-compaction pass for ``conversation_id``.

    Opens its own session so it runs independently of the request
    lifecycle and acquires the per-conversation lock so concurrent
    runs queue instead of racing.

    Caught errors are limited to provider/network/DB classes so that
    real programmer errors (``TypeError``, ``AttributeError``,
    ``ImportError`` …) surface to asyncio's default exception handler
    instead of being silently swallowed under a generic
    ``LCM_COMPACT_BG_ERR`` log line.
    """
    slot = _LCM_COMPACT_LOCKS[conversation_id]
    try:
        async with slot.lock, async_session_maker() as compact_session:
            await compact_leaf_if_needed(
                compact_session,
                conversation_id=conversation_id,
                user_id=user_id,
                model_id=model_id,
                fresh_tail_count=settings.lcm_fresh_tail_count,
                max_chunk_tokens=settings.lcm_leaf_chunk_tokens,
            )
            await compact_session.commit()
    except (OSError, RuntimeError, ValueError, TimeoutError, SQLAlchemyError):
        logger.exception(
            "LCM_COMPACT_BG_ERR conversation_id=%s",
            conversation_id,
        )
    finally:
        _release_slot(conversation_id)
