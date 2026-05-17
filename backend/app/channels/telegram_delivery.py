"""Small Telegram delivery helpers shared by channel and send-message paths."""

from __future__ import annotations

import html as html_lib
import json
import logging
from typing import TYPE_CHECKING, Any

from .telegram_html import md_to_telegram_html

if TYPE_CHECKING:
    from aiogram import Bot

    from app.core.providers.base import StreamEvent

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 4096


def format_tool_use(event: StreamEvent) -> str:
    """Render a tool call as ``icon name(['arg'])`` plus JSON input."""
    from app.integrations.telegram.tool_icons import tool_icon  # noqa: PLC0415

    tool_name = str(event.get("name") or "tool")
    raw_input = event.get("input") or {}
    input_obj = raw_input if isinstance(raw_input, dict) else {"input": raw_input}
    keys = ", ".join(repr(str(key)) for key in input_obj)
    payload = json.dumps(input_obj, ensure_ascii=False, default=str)
    return f"{tool_icon(tool_name)} {tool_name}([{keys}])\n{payload}"


def final_reply_text(
    *,
    answer_text: str,
    terminal_message: str | None,
    terminal_prefix: str,
) -> str:
    """Return final-answer copy for the dedicated reply message."""
    if answer_text and terminal_message:
        return f"{answer_text}\n\n{terminal_prefix}{terminal_message}"
    if answer_text:
        return answer_text
    if terminal_message:
        return f"{terminal_prefix}{terminal_message}"
    return ""


def plain_html(text: str) -> str:
    """Escape plain text for Telegram HTML mode."""
    return html_lib.escape(text)


def thinking_html(text: str) -> str:
    """Render thinking text as italic Telegram HTML."""
    return f"<i>{html_lib.escape(text)}</i>"


def optional_int(value: object) -> int | None:
    """Coerce optional Telegram IDs from metadata."""
    return int(value) if isinstance(value, int) else None


async def safe_edit(
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    text: str,
) -> None:
    """Call ``edit_message_text`` with Markdown-ish text."""
    await safe_edit_html(bot, chat_id, message_id, md_to_telegram_html(text))


async def safe_edit_html(
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    html: str,
) -> None:
    """Call ``edit_message_text`` with pre-rendered Telegram HTML."""
    if len(html) > MAX_MESSAGE_LEN:
        html = html[: MAX_MESSAGE_LEN - 1] + "..."
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=html,
        )
    except Exception as exc:
        err_str = str(exc).lower()
        if "not modified" in err_str:
            return
        logger.warning(
            "TELEGRAM_EDIT_FAILED chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            exc,
        )


async def safe_send_text(
    bot: Bot,
    chat_id: int | str,
    text: str,
    *,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> int | None:
    """Send Markdown-ish text after converting it to Telegram HTML."""
    return await safe_send_html(
        bot,
        chat_id,
        md_to_telegram_html(text),
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
    )


async def safe_send_html(
    bot: Bot,
    chat_id: int | str,
    html: str,
    *,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> int | None:
    """Call ``send_message`` with routing metadata, returning the message id."""
    if len(html) > MAX_MESSAGE_LEN:
        html = html[: MAX_MESSAGE_LEN - 1] + "..."
    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=html,
            **routing_kwargs(
                reply_to_message_id=reply_to_message_id,
                message_thread_id=message_thread_id,
            ),
        )
    except Exception as exc:
        logger.warning("TELEGRAM_SEND_FAILED chat_id=%s error=%s", chat_id, exc)
        return None
    message_id = getattr(sent, "message_id", None)
    return message_id if isinstance(message_id, int) else None


async def safe_delete(bot: Bot, chat_id: int | str, message_id: int) -> None:
    """Delete an unused placeholder, logging but not raising on failure."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        logger.warning(
            "TELEGRAM_DELETE_FAILED chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            exc,
        )


def routing_kwargs(
    *,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> dict[str, Any]:
    """Return Telegram send kwargs shared by turn replies and send_message."""
    kwargs: dict[str, Any] = {}
    if message_thread_id is not None:
        kwargs["message_thread_id"] = message_thread_id
    if reply_to_message_id is not None:
        from aiogram.types import ReplyParameters  # noqa: PLC0415

        kwargs["reply_parameters"] = ReplyParameters(message_id=reply_to_message_id)
    return kwargs
