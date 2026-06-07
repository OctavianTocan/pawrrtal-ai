"""Startup hook: enter the Google Chat channel lifespan.

Mirror of :mod:`app.infrastructure.startup.telegram_lifespan`. Runs just
after Telegram (``order=72`` start / ``order=38`` stop) so the two
channel lifespans bracket cleanly. A no-op when the channel is disabled
(the lifespan yields ``None``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.channels.google_chat import google_chat_lifespan
from app.infrastructure.lifecycle import shutdown_hook, startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=72)
async def start_google_chat_lifespan(app: FastAPI) -> None:
    """Enter the Google Chat lifespan and stash it on app state."""
    context_manager = google_chat_lifespan()
    service = await context_manager.__aenter__()
    app.state.google_chat_lifespan_context = context_manager
    app.state.google_chat_service = service


@shutdown_hook(order=38)
async def stop_google_chat_lifespan(app: FastAPI) -> None:
    """Exit the Google Chat lifespan if it was entered."""
    context_manager: Any | None = getattr(app.state, "google_chat_lifespan_context", None)
    if context_manager is not None:
        await context_manager.__aexit__(None, None, None)
