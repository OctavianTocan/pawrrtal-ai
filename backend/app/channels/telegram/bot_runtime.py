"""Runtime helper imports for the Telegram bot glue module.

``bot.py`` is intentionally broad because it wires aiogram to Pawrrtal's
channel runner. This module groups Telegram-local runtime helpers so the
bot module keeps a small import fan-out while the implementations stay in
focused files.
"""

from app.channels.telegram.bot_provider_resolution import resolve_provider_with_auto_clear
from app.channels.telegram.delivery import safe_edit_html
from app.channels.telegram.media_context import prepare_telegram_media_context
from app.channels.telegram.message_queue import ChatMessageQueueDispatcher, QueuedTurn
from app.channels.telegram.reasoning_notify import normalize_reasoning_and_notify
from app.channels.telegram.runtime_guards import (
    COMMAND_REFRESH_COOLDOWN_SECONDS,
    TelegramPollingLock,
    defer_command_refresh,
    should_refresh_commands,
)
from app.channels.telegram.status import (
    handle_compact_command,
    handle_lcm_command,
    handle_status_command,
)

__all__ = [
    "COMMAND_REFRESH_COOLDOWN_SECONDS",
    "ChatMessageQueueDispatcher",
    "QueuedTurn",
    "TelegramPollingLock",
    "defer_command_refresh",
    "handle_compact_command",
    "handle_lcm_command",
    "handle_status_command",
    "normalize_reasoning_and_notify",
    "prepare_telegram_media_context",
    "resolve_provider_with_auto_clear",
    "safe_edit_html",
    "should_refresh_commands",
]
