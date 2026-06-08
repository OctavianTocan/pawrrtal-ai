"""Turn finalization task tracking."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_PENDING_TURN_FINALIZE_TASKS: set[asyncio.Task[None]] = set()
_DEFAULT_FINALIZE_DRAIN_TIMEOUT_S: float = 10.0


def _register_turn_finalize_task(task: asyncio.Task[None]) -> None:
    """Track an in-flight turn finalizer so cancellation cannot GC it."""
    _PENDING_TURN_FINALIZE_TASKS.add(task)
    task.add_done_callback(_PENDING_TURN_FINALIZE_TASKS.discard)


async def await_pending_turn_finalize_tasks(
    timeout: float = _DEFAULT_FINALIZE_DRAIN_TIMEOUT_S,  # noqa: ASYNC109 - lifespan drain API
) -> None:
    """Wait for in-flight turn finalizers to finish during shutdown."""
    if not _PENDING_TURN_FINALIZE_TASKS:
        return
    pending = list(_PENDING_TURN_FINALIZE_TASKS)
    try:
        async with asyncio.timeout(timeout):
            await asyncio.gather(*pending, return_exceptions=True)
    except TimeoutError:
        outstanding = [task for task in pending if not task.done()]
        logger.warning(
            "turn_pipeline: shutdown drain timed out after %.1fs; %d finalize task(s) still running",
            timeout,
            len(outstanding),
        )
