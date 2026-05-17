"""Per-event handlers extracted from :mod:`app.channels.telegram`.

Pulled out so ``telegram.py`` stays under the 500-line ceiling enforced
by ``scripts/check-file-lines.mjs``. The functions are mechanically
identical to their previous in-file forms — no behavioural changes.

The split is along clean seams:

* :func:`prepare_tools_block` / :func:`prepare_thinking_block` — block-
  transition resets used by :meth:`TelegramChannel.deliver` (#288).
* :func:`handle_tool_use` / :func:`handle_thinking` — per-event
  Telegram I/O that ``deliver`` delegates into.
* :func:`finalize_turn_delivery` — post-stream cleanup of the
  placeholder + final-answer message (#288, #293).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.core.providers.base import StreamEvent

from .telegram_delivery import (
    format_tool_use,
    plain_html,
    safe_delete,
    safe_edit,
    safe_edit_html,
    safe_send_html,
    safe_send_text,
    thinking_html,
)

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

# Mirror constants from ``telegram.py`` rather than import them, so the
# module can be safely imported in either direction.
_EDIT_DEBOUNCE_CHARS = 40
_MAX_EDIT_INTERVAL_S = 3.0
_EMPTY_RESPONSE_FALLBACK = "⚠️ The agent finished without producing a reply. Please try again."


async def prepare_tools_block(
    *,
    previous_block_kind: str | None,
    bot: Bot,
    chat_id: int | str,
    tool_trace: str,
    tool_message_id: int,
    chars_since_edit: int,
    last_edit_at: float,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> tuple[str, int, int, float]:
    """Open a fresh tools message on a ``thinking → tools`` transition (#288).

    Returns the (possibly updated) tuple
    ``(tool_trace, tool_message_id, chars_since_edit, last_edit_at)``.
    No-op when this is the first block of either kind, or when the
    previous block was already ``tools``.
    """
    if previous_block_kind in (None, "tools"):
        return tool_trace, tool_message_id, chars_since_edit, last_edit_at
    new_id = await safe_send_html(
        bot,
        chat_id,
        plain_html("⏳"),
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
    )
    if new_id is not None:
        tool_message_id = new_id
    return "", tool_message_id, 0, asyncio.get_event_loop().time()


def prepare_thinking_block(
    *,
    previous_block_kind: str | None,
    thinking_text: str,
    thinking_message_id: int | None,
) -> tuple[str, int | None]:
    """Reset the thinking slot on a ``tools → thinking`` transition (#288)."""
    if previous_block_kind in (None, "thinking"):
        return thinking_text, thinking_message_id
    return "", None


async def handle_tool_use(
    *,
    event: StreamEvent,
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    tool_trace: str,
    chars_since_edit: int,
    last_edit_at: float,
) -> tuple[str, int, float]:
    """Inject a detailed tool-call row into the editable Telegram trace.

    Returns the updated ``(tool_trace, chars_since_edit, last_edit_at)``
    triple so the caller can flow it into the next iteration unchanged.
    """
    line = format_tool_use(event)
    tool_trace = f"{tool_trace}\n{line}" if tool_trace else line
    chars_since_edit += len(line)
    now = asyncio.get_event_loop().time()
    elapsed = now - last_edit_at
    if tool_trace and (chars_since_edit >= _EDIT_DEBOUNCE_CHARS or elapsed >= _MAX_EDIT_INTERVAL_S):
        await safe_edit_html(bot, chat_id, message_id, plain_html(tool_trace))
        return tool_trace, 0, now
    return tool_trace, chars_since_edit, last_edit_at


async def handle_thinking(
    *,
    event: StreamEvent,
    bot: Bot,
    chat_id: int | str,
    thinking_text: str,
    thinking_message_id: int | None,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> tuple[str, int | None]:
    """Send or edit the separate italic thinking message."""
    chunk = str(event.get("content") or "").strip()
    if not chunk:
        return thinking_text, thinking_message_id
    thinking_text = f"{thinking_text}\n{chunk}" if thinking_text else chunk
    html = thinking_html(thinking_text)
    if thinking_message_id is None:
        message_id = await safe_send_html(
            bot,
            chat_id,
            html,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
        )
        return thinking_text, message_id
    await safe_edit_html(bot, chat_id, thinking_message_id, html)
    return thinking_text, thinking_message_id


async def finalize_turn_delivery(
    *,
    bot: Bot,
    chat_id: int | str,
    placeholder_message_id: int,
    first_block_kind: str | None,
    previous_block_kind: str | None,
    tool_trace: str,
    thinking_text: str,
    final_text: str,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> None:
    """Resolve the ⏳ placeholder and send the closing reply (#288, #293)."""
    if first_block_kind == "tools":
        await safe_edit_html(bot, chat_id, placeholder_message_id, plain_html(tool_trace))
    elif first_block_kind == "thinking" or final_text:
        await safe_delete(bot, chat_id, placeholder_message_id)
    else:
        await safe_edit(bot, chat_id, placeholder_message_id, _EMPTY_RESPONSE_FALLBACK)
        logger.warning(
            "TELEGRAM_EMPTY_STREAM chat_id=%s message_id=%s",
            chat_id,
            placeholder_message_id,
        )

    if final_text:
        await safe_send_text(
            bot,
            chat_id,
            final_text,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
        )
        return

    if previous_block_kind == "tools" and not thinking_text:
        await safe_send_text(
            bot,
            chat_id,
            _EMPTY_RESPONSE_FALLBACK,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
        )
        logger.warning(
            "TELEGRAM_TOOL_ONLY_TURN chat_id=%s message_id=%s tool_trace_len=%d",
            chat_id,
            placeholder_message_id,
            len(tool_trace),
        )
