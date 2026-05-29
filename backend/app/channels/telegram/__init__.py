"""Telegram channel adapter.

Bridges the Telegram Bot API to Pawrrtal. Everything provider-specific
(aiogram dispatcher, message formatting, polling/webhook split) lives
here; the rest of the codebase stays Telegram-agnostic.
"""

from app.channels.telegram.bot import (
    TelegramService,
    build_telegram_service,
    telegram_lifespan,
)
from app.channels.telegram.channel import (
    SURFACE_TELEGRAM,
    TelegramChannel,
    make_telegram_sender,
    render_initial,
)

__all__ = [
    "SURFACE_TELEGRAM",
    "TelegramChannel",
    "TelegramService",
    "build_telegram_service",
    "make_telegram_sender",
    "render_initial",
    "telegram_lifespan",
]
