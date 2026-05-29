"""Startup hook: enter the Telegram channel lifespan."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.event_bus import AgentHandler, NotificationService
from app.infrastructure.lifecycle import shutdown_hook, startup_hook
from app.integrations.telegram import telegram_lifespan

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=70)
async def start_telegram_lifespan(app: FastAPI) -> None:
    """Start Telegram and register event-bus subscribers."""
    context_manager = telegram_lifespan()
    telegram_service = await context_manager.__aenter__()
    app.state.telegram_lifespan_context = context_manager
    app.state.telegram_service = telegram_service

    event_bus = getattr(app.state, "event_bus", None)
    if event_bus is None:
        return
    agent_handler = AgentHandler()
    agent_handler.register(event_bus)
    notification_service = NotificationService(
        telegram_bot=telegram_service.bot if telegram_service is not None else None
    )
    notification_service.register(event_bus)


@shutdown_hook(order=40)
async def stop_telegram_lifespan(app: FastAPI) -> None:
    """Exit the Telegram lifespan if it was entered."""
    context_manager: Any | None = getattr(app.state, "telegram_lifespan_context", None)
    if context_manager is not None:
        await context_manager.__aexit__(None, None, None)
