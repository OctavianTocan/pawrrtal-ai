"""Persistent typing-indicator helpers for the Telegram bot.

Telegram clears the "typing…" hint roughly 5 seconds after the last
``sendChatAction`` call. Refreshing on a short timer keeps the indicator
visible for the whole agent run so the user always sees that the bot is
working — matches CCT's persistent-typing behaviour.

Extracted from ``bot.py`` so ``turn_runner.py`` can stay focused on
driving the LLM pipeline rather than on Telegram's idiosyncratic
indicator refresh contract.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import ReplyParameters

logger = logging.getLogger(__name__)


async def _send_one_typing_action(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
) -> None:
    """Best-effort single ``sendChatAction`` — log and swallow on failure."""
    try:
        if thread_id is not None:
            await bot.send_chat_action(
                chat_id=chat_id,
                action="typing",
                message_thread_id=thread_id,
            )
        else:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        logger.debug(
            "TELEGRAM_TYPING_FAILED chat_id=%s thread_id=%s",
            chat_id,
            thread_id,
            exc_info=True,
        )


async def maintain_typing_indicator(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
) -> None:
    """Refresh the Telegram typing indicator on a timer until cancelled.

    Telegram clears the "typing…" hint roughly 5 seconds after the
    last ``sendChatAction`` call.  Refreshing every
    ``settings.telegram_typing_refresh_seconds`` (default 2.5s) keeps
    the indicator visible for the whole agent run so the user always
    sees that the bot is working — matches CCT's persistent-typing
    behaviour.

    Per-iteration errors are swallowed inside ``_send_one_typing_action``
    so a single failed ``sendChatAction`` never breaks the agent run.
    The whole task is cancelled by the caller's finally block.
    """
    refresh = float(settings.telegram_typing_refresh_seconds)
    try:
        while True:
            await _send_one_typing_action(bot, chat_id, thread_id)
            await asyncio.sleep(refresh)
    except asyncio.CancelledError:
        return


def reply_parameters(message_id: int) -> ReplyParameters:
    """Build aiogram reply parameters without importing aiogram at module load."""
    from aiogram.types import ReplyParameters  # noqa: PLC0415

    return ReplyParameters(message_id=message_id)
