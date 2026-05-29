"""Startup hook: create the process event bus."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.event_bus import EventBus
from app.infrastructure.event_bus.global_bus import set_event_bus
from app.infrastructure.lifecycle import shutdown_hook, startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=50)
async def start_event_bus(app: FastAPI) -> None:
    """Start the process-wide event bus and expose it on app state."""
    event_bus = EventBus()
    await event_bus.start()
    app.state.event_bus = event_bus
    set_event_bus(event_bus)


@shutdown_hook(order=50)
async def stop_event_bus(app: FastAPI) -> None:
    """Stop the process-wide event bus."""
    event_bus = getattr(app.state, "event_bus", None)
    set_event_bus(None)
    if event_bus is not None:
        await event_bus.stop()
