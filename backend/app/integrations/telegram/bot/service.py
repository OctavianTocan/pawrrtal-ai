"""aiogram-backed Telegram bot service.

Thin glue between aiogram's ``Bot`` + ``Dispatcher`` and the framework-free
handlers in :mod:`app.integrations.telegram.handlers`. Two boot modes:

- **polling** (default; works on a laptop with no inbound connectivity):
  the FastAPI lifespan launches a background task that calls
  ``Dispatcher.start_polling``. No tunnel, no ngrok, no webhook URL.

- **webhook** (production): the lifespan registers the webhook with
  Telegram on startup and the FastAPI app exposes a route that aiogram
  feeds via ``feed_webhook_update``. Set
  ``TELEGRAM_MODE=webhook`` + ``TELEGRAM_WEBHOOK_URL`` to enable.

Both paths share the same handler functions, so anything we test for
polling automatically covers webhook.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import settings
from app.integrations.telegram.bot.dispatcher import (
    register_telegram_callback_handlers,
    register_telegram_command_handlers,
    register_telegram_message_handler,
)

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher
    from aiogram.types import Update

logger = logging.getLogger(__name__)

_TELEGRAM_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Connect your Pawrrtal account"),
    ("new", "Start a new conversation"),
    ("model", "Pick or set the model (no arg = picker)"),
    ("thinking", "Pick the reasoning level for the current model"),
    ("verbose", "Set detail level: 0 quiet, 1 tools, 2 thinking"),
    ("stop", "Stop the active run"),
    ("status", "Show gateway + conversation status"),
    ("lcm", "Show LCM (long-context memory) status for this conversation"),
    ("compact", "Force an LCM leaf-compaction pass now"),
)


@dataclass
class TelegramService:
    """Holds the aiogram primitives so the lifespan can stop them cleanly."""

    bot: Bot
    dispatcher: Dispatcher
    polling_task: asyncio.Task[None] | None = None

    async def feed_webhook_update(self, update: Update) -> None:
        """Hand a single ``Update`` parsed from the webhook body to aiogram.

        Used by the FastAPI webhook route in production. Polling does
        not call this — aiogram's polling loop owns its own dispatch.
        """
        await self.dispatcher.feed_update(self.bot, update)


def build_telegram_service() -> TelegramService:
    """Construct the aiogram primitives and register the dispatcher routes.

    Raises ``RuntimeError`` if Telegram support is not configured. The
    lifespan checks the same gate before calling this so the import
    never blows up a deployment that simply doesn't use the channel.
    """
    # Local import: aiogram is only needed when the channel is wired up,
    # so a deployment without TELEGRAM_BOT_TOKEN never pays the cost.
    from aiogram import Bot, Dispatcher  # noqa: PLC0415
    from aiogram.client.default import DefaultBotProperties  # noqa: PLC0415
    from aiogram.enums import ParseMode  # noqa: PLC0415

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN must be set to start the Telegram service.")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

    register_telegram_command_handlers(dispatcher)
    register_telegram_callback_handlers(dispatcher)
    register_telegram_message_handler(dispatcher)

    return TelegramService(bot=bot, dispatcher=dispatcher)


async def refresh_telegram_commands(bot: Bot) -> None:
    """Publish the current slash-command menu to Telegram."""
    from aiogram.types import BotCommand  # noqa: PLC0415

    commands = [
        BotCommand(command=command, description=description)
        for command, description in _TELEGRAM_COMMANDS
    ]
    await bot.set_my_commands(commands)
    logger.info(
        "TELEGRAM_COMMANDS_REFRESHED commands=%s",
        ",".join(command for command, _ in _TELEGRAM_COMMANDS),
    )


async def _refresh_telegram_commands_best_effort(bot: Bot) -> None:
    """Refresh command menu without turning Telegram startup into a hard dependency."""
    try:
        await refresh_telegram_commands(bot)
    except Exception:
        logger.warning("TELEGRAM_COMMANDS_REFRESH_FAILED", exc_info=True)


@asynccontextmanager
async def telegram_lifespan() -> AsyncIterator[TelegramService | None]:
    """Lifespan-friendly context manager that boots + tears down the bot.

    Yields ``None`` when Telegram is intentionally disabled (no bot
    token) so callers can ``async with`` unconditionally without the
    callsite branching on configuration. Yields a live ``TelegramService``
    otherwise — and ensures the polling task or webhook registration is
    properly cleaned up on shutdown.
    """
    if settings.demo_mode:
        logger.info("TELEGRAM_DISABLED reason=demo_mode")
        yield None
        return
    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_DISABLED reason=no_token")
        yield None
        return

    service = build_telegram_service()
    await _refresh_telegram_commands_best_effort(service.bot)

    if settings.telegram_mode == "polling":
        # Drop any leftover webhook so polling actually receives updates;
        # Telegram silently swallows getUpdates calls when a webhook is
        # set, which is one of the most painful local-dev footguns.
        await service.bot.delete_webhook(drop_pending_updates=True)
        logger.info("TELEGRAM_BOOT mode=polling")
        service.polling_task = asyncio.create_task(
            service.dispatcher.start_polling(service.bot, handle_signals=False),
            name="telegram-polling",
        )
    else:
        url = settings.telegram_webhook_url
        if not url:
            raise RuntimeError("TELEGRAM_MODE=webhook requires TELEGRAM_WEBHOOK_URL to be set.")
        secret = settings.telegram_webhook_secret or None
        await service.bot.set_webhook(
            url=url,
            secret_token=secret,
            drop_pending_updates=True,
        )
        logger.info("TELEGRAM_BOOT mode=webhook url=%s", url)

    try:
        yield service
    finally:
        if service.polling_task is not None:
            service.polling_task.cancel()
            # The task either finishes cleanly (CancelledError) or surfaces
            # an unrelated shutdown error.  We swallow both because the
            # lifespan is already tearing down; there is nothing to recover.
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await service.polling_task
        try:
            await service.bot.session.close()
        except Exception:
            logger.warning("TELEGRAM_SHUTDOWN session_close_failed", exc_info=True)
