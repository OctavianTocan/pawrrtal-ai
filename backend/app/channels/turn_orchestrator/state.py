"""Turn finalization task tracking."""

from __future__ import annotations

import asyncio

_PENDING_TURN_FINALIZE_TASKS: set[asyncio.Task[None]] = set()


def _register_turn_finalize_task(task: asyncio.Task[None]) -> None:
    """Track an in-flight turn finalizer so cancellation cannot GC it."""
    _PENDING_TURN_FINALIZE_TASKS.add(task)
    task.add_done_callback(_PENDING_TURN_FINALIZE_TASKS.discard)
