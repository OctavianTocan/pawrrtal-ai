"""Shutdown hook: drain pending Codex thread-id persistence tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.channels.turn_runner import await_pending_codex_persist_tasks
from app.infrastructure.lifecycle import shutdown_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@shutdown_hook(order=55)
async def drain_codex_persist_tasks(app: FastAPI) -> None:
    """Wait briefly for in-flight Codex thread-id persistence to finish."""
    del app
    await await_pending_codex_persist_tasks()
