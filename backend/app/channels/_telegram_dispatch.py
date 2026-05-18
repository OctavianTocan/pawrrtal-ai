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


def capture_terminal_event(
    event: StreamEvent,
    *,
    chat_id: int | str,
    placeholder_message_id: int,
    agent_terminated_prefix: str,
    error_prefix: str,
) -> tuple[str | None, str] | None:
    """Return ``(message, prefix)`` for a terminal event, or ``None`` otherwise.

    Centralises the ``agent_terminated`` / ``error`` warning log + copy
    selection so the main deliver loop stays under the project's
    PLR0915 statement budget.
    """
    etype = event.get("type")
    if etype == "agent_terminated":
        message = event.get("content", "Agent terminated.")
        logger.warning(
            "TELEGRAM_AGENT_TERMINATED chat_id=%s message_id=%s message=%s",
            chat_id,
            placeholder_message_id,
            message,
        )
        return message, agent_terminated_prefix
    if etype == "error":
        message = event.get("content", "Unknown error.")
        logger.warning(
            "TELEGRAM_STREAM_ERROR chat_id=%s message_id=%s message=%s",
            chat_id,
            placeholder_message_id,
            message,
        )
        return message, error_prefix
    return None


async def dispatch_text_delta(
    *,
    chunk: str,
    previous_block_kind: str | None,
    bot: Bot,
    chat_id: int | str,
    text_buffer: str,
    text_message_id: int | None,
    chars_since_edit: int,
    last_edit_at: float,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> tuple[str, int | None, int, float, bool]:
    """Apply the #306 fresh-block reset (if needed) and stream the chunk.

    Returns the updated text-buffer state plus a ``rendered`` flag:

    * ``rendered=False`` for the legacy accumulate path — when no
      thinking or tool block has rendered yet, we keep the original
      "send the final answer at the end" UX for pure-text turns. The
      caller should not update ``previous_block_kind`` in that case so
      a later block still consumes the placeholder normally.
    * ``rendered=True`` when an interleaved text block was opened or
      edited in chat.
    """
    if previous_block_kind in (None, "text"):
        return text_buffer, text_message_id, chars_since_edit, last_edit_at, False
    if previous_block_kind != "text":
        # Fresh interleaved text block — reset the streaming slot so
        # the new Telegram message starts clean.
        text_message_id = None
        text_buffer = ""
        chars_since_edit = 0
        last_edit_at = asyncio.get_event_loop().time()
    (
        text_buffer,
        text_message_id,
        chars_since_edit,
        last_edit_at,
    ) = await handle_text_delta(
        chunk=chunk,
        bot=bot,
        chat_id=chat_id,
        text_buffer=text_buffer,
        text_message_id=text_message_id,
        chars_since_edit=chars_since_edit,
        last_edit_at=last_edit_at,
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
    )
    return text_buffer, text_message_id, chars_since_edit, last_edit_at, True


async def handle_text_delta(
    *,
    chunk: str,
    bot: Bot,
    chat_id: int | str,
    text_buffer: str,
    text_message_id: int | None,
    chars_since_edit: int,
    last_edit_at: float,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> tuple[str, int | None, int, float]:
    """Append ``chunk`` to the live text message — open one if needed (#306).

    Mirrors :func:`handle_tool_use` debounce: only edits once we have
    enough new chars or enough elapsed time so we don't hammer
    Telegram with one ``edit_message_text`` per token.
    """
    if not chunk:
        return text_buffer, text_message_id, chars_since_edit, last_edit_at
    text_buffer = f"{text_buffer}{chunk}"
    if text_message_id is None:
        new_id = await safe_send_text(
            bot,
            chat_id,
            text_buffer,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
        )
        return text_buffer, new_id, 0, asyncio.get_event_loop().time()
    chars_since_edit += len(chunk)
    now = asyncio.get_event_loop().time()
    elapsed = now - last_edit_at
    if chars_since_edit >= _EDIT_DEBOUNCE_CHARS or elapsed >= _MAX_EDIT_INTERVAL_S:
        await safe_edit(bot, chat_id, text_message_id, text_buffer)
        return text_buffer, text_message_id, 0, now
    return text_buffer, text_message_id, chars_since_edit, last_edit_at


async def finalize_turn_delivery(
    *,
    bot: Bot,
    chat_id: int | str,
    placeholder_message_id: int,
    first_block_kind: str | None,
    previous_block_kind: str | None,
    tool_trace: str,
    thinking_text: str,
    text_message_id: int | None,
    text_buffer: str,
    final_text: str,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> None:
    """Resolve the ⏳ placeholder and send the closing reply (#288, #293, #306).

    When ``text_message_id`` is set, an in-stream text message is
    already on screen — we flush its final buffer in place and skip
    the closing ``final_text`` send so the user doesn't see the
    answer twice.
    """
    if first_block_kind == "tools":
        await safe_edit_html(bot, chat_id, placeholder_message_id, plain_html(tool_trace))
    elif first_block_kind in ("thinking", "text") or final_text:
        await safe_delete(bot, chat_id, placeholder_message_id)
    else:
        await safe_edit(bot, chat_id, placeholder_message_id, _EMPTY_RESPONSE_FALLBACK)
        logger.warning(
            "TELEGRAM_EMPTY_STREAM chat_id=%s message_id=%s",
            chat_id,
            placeholder_message_id,
        )

    if text_message_id is not None and text_buffer:
        # Final flush so the last debounced chunk lands even if we
        # were inside the debounce window when the stream ended.
        await safe_edit(bot, chat_id, text_message_id, text_buffer)
        return

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
