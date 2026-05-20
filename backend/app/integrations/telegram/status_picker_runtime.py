"""aiogram runtime + per-panel formatters for the interactive /status picker (#361).

Mirrors the established :mod:`thinking_picker_runtime` /
:mod:`verbose_picker_runtime` layout — keeps the picker module
framework-free for unit tests while this file owns the aiogram-
shaped IO and the per-panel formatters.

Each ``StatusPanel`` callback posts a follow-up message scoped
to that section. The legacy monolithic ``/status`` reply stays
available behind ``/status all`` for power users (wired in
``bot.py``).
"""

from __future__ import annotations

import logging
from html import escape
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import async_session_maker
from app.integrations.telegram.handlers import TelegramSender
from app.integrations.telegram.status_picker import (
    STATUS_CALLBACK_PREFIX,  # noqa: F401 — re-exported so bot.py imports both via one module
    StatusButton,
    StatusPanel,
    build_status_keyboard,
    panel_label,
    parse_status_callback_data,
    status_picker_header,
)
from app.integrations.telegram.thinking_picker import PROVIDER as _TELEGRAM_PROVIDER
from app.crud.channel import (
    get_or_create_telegram_conversation_full,
    get_user_id_for_external,
)
from app.crud.conversation import get_conversation_status

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)


_PANEL_NOT_BOUND_MESSAGE = "Connect your account first before opening status."
_PANEL_STALE_MESSAGE = "That status picker is out of date. Open /status again."


async def answer_status_picker(*, message: Message) -> None:
    """Open the interactive ``/status`` panel keyboard."""
    await message.answer(
        status_picker_header(),
        reply_markup=_inline_keyboard(build_status_keyboard()),
        reply_parameters=_reply_parameters(message.message_id),
    )


async def handle_status_picker_callback(*, callback: CallbackQuery) -> None:
    """Handle inline-keyboard callbacks produced by the status picker."""
    parsed = parse_status_callback_data(callback.data)
    if parsed is None:
        await callback.answer(_PANEL_STALE_MESSAGE, show_alert=True)
        return

    sender = _sender_from_callback(callback)
    body = await _render_panel(sender=sender, panel=parsed.panel)

    message = _callback_message(callback)
    if message is None:
        await callback.answer(_PANEL_STALE_MESSAGE, show_alert=True)
        return
    await message.answer(body, reply_parameters=_reply_parameters(message.message_id))
    await callback.answer(f"{panel_label(parsed.panel)} ✓")


async def _render_panel(*, sender: TelegramSender, panel: StatusPanel) -> str:
    """Dispatch to the per-panel formatter and return the message body."""
    async with async_session_maker() as session:
        pawrrtal_user_id = await get_user_id_for_external(
            provider=_TELEGRAM_PROVIDER,
            external_user_id=str(sender.user_id),
            session=session,
        )
        if pawrrtal_user_id is None:
            return _PANEL_NOT_BOUND_MESSAGE
        if panel is StatusPanel.SYSTEM:
            return _render_system_panel()
        if panel is StatusPanel.CONVERSATION:
            return await _render_conversation_panel(
                sender=sender,
                session=session,
                pawrrtal_user_id=pawrrtal_user_id,
            )
        if panel is StatusPanel.USAGE:
            return await _render_usage_panel(
                sender=sender,
                session=session,
                pawrrtal_user_id=pawrrtal_user_id,
            )
        if panel is StatusPanel.TOOLS:
            return _render_tools_panel()
        if panel is StatusPanel.LCM:
            return _render_lcm_panel()
        if panel is StatusPanel.COMMANDS:
            return _render_commands_panel()
    return _PANEL_STALE_MESSAGE


def _render_system_panel() -> str:
    """Gateway uptime + default model + dev-mode flag."""
    from app.core.providers.catalog import default_model  # noqa: PLC0415
    from app.integrations.telegram.bot import get_bot_uptime_seconds  # noqa: PLC0415

    uptime_seconds = get_bot_uptime_seconds()
    return (
        "🌐 <b>System</b>\n\n"
        f"⏱  Bot uptime: {_format_duration(uptime_seconds)}\n"
        f"🤖 Default model: <b>{escape(default_model().short_name)}</b>\n"
        f"🛠  Environment: <b>{escape(settings.env)}</b>\n"
        f"🔊 Default verbose: <b>{settings.telegram_verbose_default}</b>"
    )


async def _render_conversation_panel(
    *,
    sender: TelegramSender,
    session: AsyncSession,
    pawrrtal_user_id: object,
) -> str:
    """Per-conversation summary — model, verbose, thinking, run-state."""
    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,  # type: ignore[arg-type]
        session=session,
        thread_id=sender.thread_id,
    )
    return (
        "💬 <b>Conversation</b>\n\n"
        f"🤖 Model: <b>{escape(conversation.model_id or '(default)')}</b>\n"
        f"🔊 Verbose: <b>{conversation.verbose_level if conversation.verbose_level is not None else '(default)'}</b>\n"
        f"🧠 Thinking: <b>{escape(conversation.reasoning_effort or '(default)')}</b>"
    )


async def _render_usage_panel(
    *,
    sender: TelegramSender,
    session: AsyncSession,
    pawrrtal_user_id: object,
) -> str:
    """Token + cost ledger for the current conversation."""
    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,  # type: ignore[arg-type]
        session=session,
        thread_id=sender.thread_id,
    )
    status = await get_conversation_status(
        conversation_id=conversation.id,
        session=session,
    )
    if status is None:
        return "📊 <b>Usage</b>\n\nNo data yet for this conversation."
    return (
        "📊 <b>Usage</b>\n\n"
        f"💬 Messages: {status.message_count} "
        f"({status.user_message_count} yours, {status.assistant_message_count} assistant)\n"
        f"🔢 Input tokens: {status.total_input_tokens:,}\n"
        f"🔢 Output tokens: {status.total_output_tokens:,}\n"
        f"💵 Cost: ${status.total_cost_usd:.4f}"
    )


def _render_tools_panel() -> str:
    """List the tools the active model has available this turn.

    Today this is a static surface — the chat router composes the
    actual tool list per turn so we don't have a per-conversation
    snapshot to read. Surfacing the toggles (LCM enabled? Exa
    configured? send_image plugged in?) gives operators the most
    useful signal without rebuilding ``build_agent_tools``.
    """
    lcm_status = "✅ on" if settings.lcm_enabled else "⏸ off"
    exa_status = "✅ on" if settings.exa_api_key else "⏸ unconfigured"
    return (
        "🔧 <b>Tools</b>\n\n"
        f"LCM history: <b>{lcm_status}</b>\n"
        f"Exa web search: <b>{exa_status}</b>\n"
        "send_image / Telegram capabilities: <b>✅ on</b> for Telegram surface"
    )


def _render_lcm_panel() -> str:
    """LCM pull / push status — toggle, background worker, embedding model."""
    background = "✅ on" if settings.lcm_background_enabled else "⏸ off"
    return (
        "🧠 <b>LCM</b>\n\n"
        f"Master switch: <b>{'✅ on' if settings.lcm_enabled else '⏸ off'}</b>\n"
        f"Background worker: <b>{background}</b>"
    )


def _render_commands_panel() -> str:
    """The slash-command surface the user can invoke."""
    return (
        "📋 <b>Commands</b>\n\n"
        "/start — register this Telegram account\n"
        "/new — start a fresh conversation\n"
        "/model — pick a model\n"
        "/thinking — pick a reasoning level\n"
        "/verbose — pick a verbose level\n"
        "/stop — cancel the current turn\n"
        "/status — open this panel\n"
        "/lcm — LCM status\n"
        "/compact — compact the LCM"
    )


def _format_duration(seconds: float) -> str:
    """Render a duration as ``"3d 1h"`` / ``"4h 12m"`` / ``"34s"``."""
    total = int(max(0.0, seconds))
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _inline_keyboard(rows: list[list[StatusButton]]) -> object:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: PLC0415

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=button.text, callback_data=button.callback_data)
                for button in row
            ]
            for row in rows
        ]
    )


def _sender_from_callback(callback: CallbackQuery) -> TelegramSender:
    message = _callback_message(callback)
    if message is None:
        raise RuntimeError("Telegram callback has no accessible message.")
    user = callback.from_user
    return TelegramSender(
        user_id=user.id,
        chat_id=message.chat.id,
        username=user.username,
        full_name=user.full_name,
        thread_id=message.message_thread_id,
    )


def _callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    if message is None or not hasattr(message, "answer"):
        return None
    return message


def _reply_parameters(message_id: int) -> object:
    from aiogram.types import ReplyParameters  # noqa: PLC0415

    return ReplyParameters(message_id=message_id)
