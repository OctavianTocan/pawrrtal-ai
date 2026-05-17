"""Telegram channel adapter.

Bridges the Telegram Bot API to Pawrrtal. Everything provider-specific
(aiogram dispatcher, message formatting, polling/webhook split) lives
here; the rest of the codebase stays Telegram-agnostic.
"""

from app.integrations.telegram.bot import (
    TelegramService,
    build_telegram_service,
    telegram_lifespan,
)

__all__ = ["TelegramService", "build_telegram_service", "telegram_lifespan"]
