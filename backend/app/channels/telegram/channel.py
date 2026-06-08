"""TelegramChannel — progressive message-edit delivery via aiogram.

Delivers LLM stream events by calling ``bot.edit_message_text`` / aiogram
methods as chunks arrive.  All delivery is a side-effect; the async iterator
yields nothing.

Debounce: edits fire when ``_EDIT_DEBOUNCE_CHARS`` new chars accumulate
or ``_MAX_EDIT_INTERVAL_S`` seconds elapse.  Final edit always fires.

Non-text outcomes replace the placeholder with a user-facing message. Empty
and tool-only turns also surface a closing reply so the user knows the turn ended.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.channels.base import ChannelMessage
from app.infrastructure.config import settings
from app.providers.base import StreamEvent
from app.tools.send_message import SendFn

from .delivery import (
    final_reply_text,
    optional_int,
    routing_kwargs,
    safe_edit_html,
)
from .dispatch import (
    ToolLineState,
    capture_terminal_event,
    finalize_turn_delivery,
    handle_thinking,
    handle_tool_progress,
    handle_tool_result,
    handle_tool_use,
    prepare_thinking_block,
    prepare_tools_block,
)
from .html import md_to_telegram_html
from .progress import render_initial as render_initial  # noqa: PLC0414
from .progress import render_transient_status
from .text_delivery import TextDeliveryState, handle_delta_event

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

SURFACE_TELEGRAM = "telegram"

# Prefix glyphs for non-text outcomes (short to avoid crowding the message).
_AGENT_TERMINATED_PREFIX = "⚠️ "
_ERROR_PREFIX = "❌ "

# Fallback copy used when a turn produces neither text nor a structured
# termination/error event.  Without this the ⏳ placeholder would sit forever
# and the user would never know the turn ended.  Avoid mentioning server-side
# paths here — this string is rendered directly into the user's Telegram chat
# and shouldn't leak internal infrastructure.
_EMPTY_RESPONSE_FALLBACK = "⚠️ The agent finished without producing a reply. Please try again."


def _build_regenerate_markup(conversation_id: Any) -> Any | None:
    """Build the regenerate inline keyboard when the feature flag is on."""
    if not settings.telegram_regenerate_button_enabled:
        return None
    from app.channels.telegram.regenerate_keyboard import regenerate_markup_for  # noqa: PLC0415

    return regenerate_markup_for(conversation_id)


class TelegramChannel:
    """``Channel`` implementation for Telegram, using aiogram message edits.

    Instantiated once and shared across requests — it holds no per-request
    state.  All per-request context (bot reference, chat/message IDs) travels
    through ``ChannelMessage.metadata``.
    """

    surface: str = SURFACE_TELEGRAM

    async def deliver(  # noqa: PLR0915
        self,
        stream: AsyncIterator[StreamEvent],
        message: ChannelMessage,
    ) -> AsyncIterator[bytes]:
        """Consume LLM events and deliver the Telegram turn as separate messages.

        Expected ``message["metadata"]`` keys:

        - ``bot`` (``aiogram.Bot``): live bot instance.
        - ``chat_id`` (``int | str``): target Telegram chat.
        - ``message_id`` (``int``): placeholder message to overwrite.

        Yields nothing — all delivery is via side-effects.

        Args:
            stream: Async iterator of ``StreamEvent`` dicts from the LLM.
            message: Originating ``ChannelMessage`` — metadata carries the
                     Telegram-specific routing context.
        """
        meta: dict[str, Any] = message["metadata"]
        bot: Bot = meta["bot"]
        chat_id = meta["chat_id"]
        message_id: int = meta["message_id"]
        reply_to_message_id = optional_int(meta.get("reply_to_message_id"))
        message_thread_id = optional_int(meta.get("message_thread_id"))
        reply_markup = _build_regenerate_markup(message["conversation_id"])

        tool_trace = ""
        tool_states: dict[str, ToolLineState] = {}

        # ``tool_message_id`` starts as the placeholder so the FIRST tools
        # block consumes it; later block transitions open fresh messages.
        tool_message_id: int = message_id
        text_state = TextDeliveryState(last_edit_at=asyncio.get_event_loop().time())
        thinking_text = ""
        thinking_message_id: int | None = message_id
        chars_since_edit = 0
        last_edit_at = asyncio.get_event_loop().time()
        # ``previous_thinking_block_index`` tracks the ``block_index``
        # of the most recent thinking event so ``handle_thinking`` can
        # insert a paragraph break only when a new block starts.
        # ``None`` before the first thinking event so the very first
        # chunk does not get a leading separator.
        previous_thinking_block_index: int | None = None
        # The active block is finalized when the stream switches between
        # thinking and tool output, so Telegram reads chronologically.
        previous_block_kind: str | None = None
        # ``first_block_kind`` records what the placeholder was used for,
        # so the post-stream cleanup can tell whether ⏳ holds real content
        # (first block was tools — keep it) or is still the dangling
        # placeholder (first block was thinking — delete it).
        first_block_kind: str | None = None

        # Captured terminal outcomes — flushed after the stream ends so they
        # don't race the in-flight debounced edits for ``delta`` chunks.
        terminal_message: str | None = None
        terminal_prefix: str = ""

        # Content-preview-in-placeholder state machine. The placeholder
        # opens with ``render_initial()`` and advances to WORKING when
        # the first text delta arrives so the user sees the answer
        # forming inside the placeholder. Tool turns let
        # ``handle_tool_use`` overwrite the placeholder with the tools
        # header directly — no intermediate "Starting…" banner.
        # Re-paint the placeholder defensively. The caller (bot.py) creates
        # it with the same text, so Telegram returns "message not modified"
        # which ``safe_edit_html`` silently swallows. This keeps deliver()
        # self-sufficient if the placeholder is ever opened with a different
        # text (e.g. a future caller, tests).
        await safe_edit_html(bot, chat_id, message_id, render_initial())

        async for event in stream:
            etype = event.get("type")

            if event.get("transient"):
                if first_block_kind is None:
                    await safe_edit_html(
                        bot,
                        chat_id,
                        message_id,
                        render_transient_status(str(event.get("content") or "Working")),
                    )
                continue

            if etype == "tool_use":
                first_block_kind = (
                    "tools" if first_block_kind in (None, "text") else first_block_kind
                )
                (
                    tool_trace,
                    tool_message_id,
                    chars_since_edit,
                    last_edit_at,
                ) = await prepare_tools_block(
                    previous_block_kind=previous_block_kind,
                    bot=bot,
                    chat_id=chat_id,
                    tool_trace=tool_trace,
                    tool_message_id=tool_message_id,
                    chars_since_edit=chars_since_edit,
                    last_edit_at=last_edit_at,
                    reply_to_message_id=reply_to_message_id,
                    message_thread_id=message_thread_id,
                    tool_states=tool_states,
                )
                previous_block_kind = "tools"
                tool_trace, chars_since_edit, last_edit_at = await handle_tool_use(
                    event=event,
                    bot=bot,
                    chat_id=chat_id,
                    message_id=tool_message_id,
                    tool_trace=tool_trace,
                    chars_since_edit=chars_since_edit,
                    last_edit_at=last_edit_at,
                    tool_states=tool_states,
                )
                continue

            if etype in {"tool_result", "tool_progress"}:
                tool_handler = (
                    handle_tool_result if etype == "tool_result" else handle_tool_progress
                )
                tool_trace, chars_since_edit, last_edit_at = await tool_handler(
                    event=event,
                    bot=bot,
                    chat_id=chat_id,
                    message_id=tool_message_id,
                    tool_trace=tool_trace,
                    chars_since_edit=chars_since_edit,
                    last_edit_at=last_edit_at,
                    tool_states=tool_states,
                )
                continue

            if etype == "thinking":
                first_block_kind = (
                    "thinking" if first_block_kind in (None, "text") else first_block_kind
                )
                thinking_text, thinking_message_id = prepare_thinking_block(
                    previous_block_kind=previous_block_kind,
                    thinking_text=thinking_text,
                    thinking_message_id=thinking_message_id,
                )
                # Reset the block-index baseline whenever the prepare step
                # opens a fresh thinking message (tools→thinking transition).
                # Otherwise the carry-over index could trigger a leading
                # paragraph break inside the new italic message.
                if thinking_message_id is None:
                    previous_thinking_block_index = None
                previous_block_kind = "thinking"
                (
                    thinking_text,
                    thinking_message_id,
                    previous_thinking_block_index,
                ) = await handle_thinking(
                    event=event,
                    bot=bot,
                    chat_id=chat_id,
                    thinking_text=thinking_text,
                    thinking_message_id=thinking_message_id,
                    previous_thinking_block_index=previous_thinking_block_index,
                    reply_to_message_id=reply_to_message_id,
                    message_thread_id=message_thread_id,
                )
                continue

            if etype == "delta":
                rendered = await handle_delta_event(
                    event=event,
                    bot=bot,
                    chat_id=chat_id,
                    placeholder_message_id=message_id,
                    text_state=text_state,
                    first_block_kind=first_block_kind,
                    previous_block_kind=previous_block_kind,
                    reply_to_message_id=reply_to_message_id,
                    message_thread_id=message_thread_id,
                )
                if rendered:
                    # Legacy interleaved-text path: the chunk landed in a
                    # separate Telegram message, so the placeholder is now
                    # "consumed" and the next tool/thinking block must open
                    # a fresh message.
                    first_block_kind = first_block_kind or "text"
                    previous_block_kind = "text"
                continue

            captured = capture_terminal_event(
                event,
                chat_id=chat_id,
                placeholder_message_id=message_id,
                agent_terminated_prefix=_AGENT_TERMINATED_PREFIX,
                error_prefix=_ERROR_PREFIX,
            )
            if captured is not None:
                terminal_message, terminal_prefix = captured
                continue

        # When text was already rendered progressively into its own Telegram
        # message, skip the closing answer duplicate.
        # Any terminal_message (error / agent_terminated) flushes regardless.
        final_text = final_reply_text(
            answer_text="" if text_state.message_id is not None else text_state.answer_text,
            terminal_message=terminal_message,
            terminal_prefix=terminal_prefix,
        )
        await finalize_turn_delivery(
            bot=bot,
            chat_id=chat_id,
            placeholder_message_id=message_id,
            first_block_kind=first_block_kind,
            previous_block_kind=previous_block_kind,
            tool_trace=tool_trace,
            thinking_text=thinking_text,
            text_message_id=text_state.message_id,
            text_buffer=text_state.buffer,
            final_text=final_text,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
            reply_markup=reply_markup,
        )

        # No bytes to yield — delivery is a side-effect only.
        return
        # The bare ``yield`` below is unreachable but required: it makes
        # this function an async generator (the Channel.deliver protocol
        # signature), so callers can ``async for`` over it even though we
        # only ever side-effect through ``edit_message_text``.
        yield


# ---------------------------------------------------------------------------
# MIME-aware media sender factory
# ---------------------------------------------------------------------------


def make_telegram_sender(
    bot: Bot,
    chat_id: int | str,
    *,
    message_thread_id: int | None = None,
    reply_to_message_id: int | None = None,
) -> SendFn:
    """Return a :data:`~app.tools.send_message.SendFn` for Telegram.

    The returned coroutine routes delivery based on MIME type::

        image/*          → bot.send_photo(file, caption=text)
        audio/ogg        → bot.send_voice(file)          # Telegram renders as voice
        audio/opus       → bot.send_voice(file)
        audio/*          → bot.send_audio(file, caption=text)
        video/*          → bot.send_video(file, caption=text)
        *                → bot.send_document(file, caption=text)

    Text-only calls (no file) fall through to ``bot.send_message``.

    When *message_thread_id* is set every call includes it so the reply
    lands in the correct Telegram topic thread. When *reply_to_message_id*
    is set, every sent payload threads under the triggering user message.

    Args:
        bot: Live aiogram ``Bot`` instance.
        chat_id: Target Telegram chat ID.
        message_thread_id: Optional topic thread ID (Bot API 9.3+).
            Pass ``None`` (the default) for DMs without topics enabled.
        reply_to_message_id: Optional inbound message id to reply to.

    Returns:
        An async :data:`~app.tools.send_message.SendFn` callback ready
        to pass to :func:`~app.tools.send_message.make_send_message_tool`.
    """

    async def _send(
        text: str | None,
        file_path: Path | None,
        mime: str | None,
    ) -> None:
        route_kwargs = routing_kwargs(
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
        )

        if file_path is None:
            # Text-only delivery.
            await bot.send_message(
                chat_id=chat_id,
                text=md_to_telegram_html(text or ""),
                **route_kwargs,
            )
            return

        from aiogram.types import FSInputFile  # noqa: PLC0415 — lazy import; aiogram optional

        file = FSInputFile(file_path)
        caption = md_to_telegram_html(text) if text else None
        m = (mime or "").lower()

        if m.startswith("image/"):
            await bot.send_photo(
                chat_id=chat_id,
                photo=file,
                caption=caption,
                **route_kwargs,
            )
            return
        if m in ("audio/ogg", "audio/opus"):
            # Telegram renders ogg/opus as an in-chat voice note.
            await bot.send_voice(
                chat_id=chat_id,
                voice=file,
                caption=caption,
                **route_kwargs,
            )
            return
        if m.startswith("audio/"):
            await bot.send_audio(
                chat_id=chat_id,
                audio=file,
                caption=caption,
                **route_kwargs,
            )
            return
        if m.startswith("video/"):
            await bot.send_video(
                chat_id=chat_id,
                video=file,
                caption=caption,
                **route_kwargs,
            )
            return
        # Fallback — send as a downloadable document.
        await bot.send_document(
            chat_id=chat_id,
            document=file,
            caption=caption,
            **route_kwargs,
        )

    return _send
