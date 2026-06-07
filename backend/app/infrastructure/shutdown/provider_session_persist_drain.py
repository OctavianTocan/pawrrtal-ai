"""Shutdown hook: drain pending provider-session persistence tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.lifecycle import shutdown_hook
from app.provider_sessions import await_pending_provider_session_persist_tasks

if TYPE_CHECKING:
    from fastapi import FastAPI


@shutdown_hook(order=55)
async def drain_provider_session_persist_tasks(app: FastAPI) -> None:
    """Wait briefly for in-flight provider-session persistence to finish."""
    del app
    await await_pending_provider_session_persist_tasks()
