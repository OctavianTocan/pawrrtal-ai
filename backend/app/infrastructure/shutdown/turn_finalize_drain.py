"""Shutdown hook: drain pending turn finalization tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.channels.turn_orchestrator.state import await_pending_turn_finalize_tasks
from app.infrastructure.lifecycle import shutdown_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@shutdown_hook(order=56)
async def drain_turn_finalize_tasks(app: FastAPI) -> None:
    """Wait briefly for in-flight turn finalizers to finish."""
    del app
    await await_pending_turn_finalize_tasks()
