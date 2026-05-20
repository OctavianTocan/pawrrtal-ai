"""Module-global state for the Telegram bot package.

Centralises the two module-globals shared by every file in the
``bot/`` package so importers all read and write the **same**
singleton dict / start timestamp. Without this, the polling task
written by ``service.py`` and the ``/stop`` cancellation in
``dispatcher.py`` would see two different dicts and the cancellation
would silently no-op.
"""

from __future__ import annotations

import asyncio
import time

# Captured at module import so /status can report this worker's uptime
# without reading the wall clock at boot. Process-local — multi-worker
# deployments report only the worker that handled the command.
_BOT_START_MONOTONIC: float = time.monotonic()


def get_bot_uptime_seconds() -> float:
    """Return seconds since this worker's process started."""
    return time.monotonic() - _BOT_START_MONOTONIC


def is_chat_run_active(chat_id: int) -> bool:
    """Return whether an agent run is in flight for ``chat_id`` on this worker."""
    task = _running_tasks.get(chat_id)
    return task is not None and not task.done()


# Active streaming tasks keyed by Telegram chat_id.  When a new message
# arrives we cancel any existing task for that chat (preventing two parallel
# streams into the same placeholder message), then store the new one so
# a subsequent /stop can cancel it.
#
# IMPORTANT — this dict is PROCESS-LOCAL.  A /stop arriving on worker A
# cannot cancel a task running on worker B.  This is correct for the current
# single-worker deployment; promote to a shared store (e.g. Redis pub/sub)
# before running multiple uvicorn workers.
#
# This is the SINGLE source of truth for the dict — every other module in
# this package imports it from here so they all read/write the same dict.
_running_tasks: dict[int, asyncio.Task[None]] = {}
