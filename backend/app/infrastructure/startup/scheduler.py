"""Startup hook: start the optional cron scheduler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.scheduling import JobScheduler, set_active_scheduler
from app.infrastructure.config import settings
from app.infrastructure.lifecycle import shutdown_hook, startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=60)
async def start_scheduler(app: FastAPI) -> None:
    """Start APScheduler when scheduler support is enabled."""
    if not settings.scheduler_enabled:
        app.state.scheduler = None
        set_active_scheduler(None)
        return
    scheduler = JobScheduler()
    await scheduler.start()
    app.state.scheduler = scheduler
    set_active_scheduler(scheduler)


@shutdown_hook(order=60)
async def stop_scheduler(app: FastAPI) -> None:
    """Stop the active scheduler if one was started."""
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        await scheduler.stop()
    set_active_scheduler(None)
