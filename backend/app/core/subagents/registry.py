"""In-process registry of live subagent ``asyncio.Task`` references.

Holds **strong references** to every running subagent task so the
asyncio event loop doesn't garbage-collect them (bpo-44665 — tasks
created without a strong ref disappear silently and never run to
completion).  Keyed by stable subagent handle so the cascade-cancel
hook and the ``cancel_subagent`` tool can both reach into the
registry by name.

Per-worker.  The dict only contains tasks spawned on **this** FastAPI
worker; a cancel coming from another worker can't reach them via this
registry.  That's by design — the DB row is the cross-worker
authoritative signal (see ``cancel_running_subagents_for_conversation``).
The registry is the in-process fast path, not the durable one.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


_live_tasks: dict[str, asyncio.Task[None]] = {}


def register(handle: str, task: asyncio.Task[None]) -> None:
    """Store a strong reference to ``task`` under ``handle``.

    Attaches a ``done_callback`` that removes the entry once the task
    finishes — keeps the dict from growing without bound across long
    server lifetimes.  Idempotent on duplicate handles (the new task
    overwrites the old; in practice the spawn flow's UNIQUE constraint
    on ``subagents.handle`` prevents the duplicate from being created
    in the first place).
    """
    _live_tasks[handle] = task
    task.add_done_callback(lambda _t: _live_tasks.pop(handle, None))


def cancel(handle: str) -> bool:
    """Best-effort cancel of the live task for ``handle``.

    Returns ``True`` when a live task ref was found and ``.cancel()``
    was issued; ``False`` when no ref exists on this worker (the task
    is either already finished or running on a different worker).
    The DB row is the cross-worker truth — the runner re-reads
    ``status`` between iterations and bails when it sees anything
    other than ``"running"``.
    """
    task = _live_tasks.get(handle)
    if task is None:
        return False
    if task.done():
        return False
    task.cancel()
    logger.info("SUBAGENT_REGISTRY_CANCEL handle=%s", handle)
    return True


def is_alive(handle: str) -> bool:
    """Return whether a live (non-done) task exists on this worker."""
    task = _live_tasks.get(handle)
    return task is not None and not task.done()


def live_handles() -> list[str]:
    """Return a snapshot of currently-tracked handles.

    Test-only / diagnostic — production code should query the
    ``subagents`` table for cross-worker truth.
    """
    return [h for h, t in _live_tasks.items() if not t.done()]


def clear() -> None:
    """Cancel every live task and drop all refs.  Test-only."""
    for task in list(_live_tasks.values()):
        if not task.done():
            task.cancel()
    _live_tasks.clear()


__all__ = ["cancel", "clear", "is_alive", "live_handles", "register"]
