"""TelegramChannel — progressive message-edit delivery via aiogram.

Delivers LLM stream events by calling ``bot.edit_message_text`` / aiogram
methods as chunks arrive.  All delivery is a side-effect; the async iterator
yields nothing.

Debounce: edits fire when ``_EDIT_DEBOUNCE_CHARS`` new chars accumulate
or ``_MAX_EDIT_INTERVAL_S`` seconds elapse.  Final edit always fires.

Non-text outcomes (agent_terminated, error) replace the ⏳ placeholder
with a user-facing message.  "Empty stream" and "tool-only turn" (#293)
also surface a closing reply so the user always knows the turn ended.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.providers.base import StreamEvent
from app.core.tools.send_message import SendFn

from ._telegram_dispatch import (
    DraftStreamState,
    ToolLineState,
    capture_terminal_event,
    dispatch_text_delta,
    finalize_turn_delivery,
    handle_thinking,
    handle_tool_result,
    handle_tool_use,
    prepare_thinking_block,
    prepare_tools_block,
)
from ._telegram_draft import _TEXT_DRAFT_ID
from .base import ChannelMessage
from .telegram_delivery import (
    final_reply_text,
    optional_int,
    routing_kwargs,
    safe_edit_html,
)
from .telegram_html import md_to_telegram_html
from .telegram_progress import ProgressState, render_working
from .telegram_progress import render_initial as render_initial  # noqa: PLC0414

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

SURFACE_TELEGRAM = "telegram"

# Send an edit when this many new characters have accumulated since the last
# edit.  Keeps the perceived update cadence snappy without hammering the API.
_EDIT_DEBOUNCE_CHARS = 40

# Hard upper bound between edits in wall-clock seconds.  Ensures the user
# sees *something* change even when the model emits many tiny tokens.
_MAX_EDIT_INTERVAL_S = 3.0

# Prefix glyphs for non-text outcomes so the user can spot terminations and
# errors at a glance in their chat.  These are deliberately short so they
# don't crowd out the actual message body.
_AGENT_TERMINATED_PREFIX = "⚠️ "
_ERROR_PREFIX = "❌ "

# Fallback copy used when a turn produces neither text nor a structured
# termination/error event.  Without this the ⏳ placeholder would sit forever
# and the user would never know the turn ended.  Avoid mentioning server-side
# paths here — this string is rendered directly into the user's Telegram chat
# and shouldn't leak internal infrastructure.
_EMPTY_RESPONSE_FALLBACK = "⚠️ The agent finished without producing a reply. Please try again."


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

        tool_trace = ""
        # Per-tool state dict for Workstream 4 success/failure timing.
        # Keyed by tool call_id; maps to ToolLineState so tool_result
        # events can mutate in-flight lines to show timing/errors.
        tool_states: dict[str, ToolLineState] = {}
        # Workstream 1: draft streaming state. Created only when the flag
        # is enabled so the legacy editMessageText path is unchanged.
        draft_state: DraftStreamState | None = (
            DraftStreamState(
                chat_id=chat_id,
                draft_id=_TEXT_DRAFT_ID,
                message_thread_id=message_thread_id,
            )
            if settings.telegram_use_draft_streaming
            else None
        )
        # ``tool_message_id`` starts as the placeholder so the FIRST tools
        # block consumes the ⏳; on a thinking→tools transition (issue #288)
        # we open a fresh Telegram message for the new tools block and
        # rebind this slot so subsequent edits land there.
        tool_message_id: int = message_id
        answer_text = ""
        thinking_text = ""
        thinking_message_id: int | None = message_id
        # #306/#307: interleaved text deltas open their own Telegram
        # messages in chronological order. ``text_message_id`` tracks
        # the open text message; ``text_chars_since_edit`` and
        # ``text_last_edit_at`` drive the debounce mirroring the tools
        # path. On a text → tools/thinking transition,
        # ``prepare_text_block`` resets the slot so the next delta
        # opens a fresh message.
        text_buffer = ""
        text_message_id: int | None = None
        text_chars_since_edit = 0
        text_last_edit_at = asyncio.get_event_loop().time()
        chars_since_edit = 0
        last_edit_at = asyncio.get_event_loop().time()
        # ``previous_thinking_block_index`` tracks the ``block_index``
        # of the most recent thinking event so ``handle_thinking`` can
        # insert a paragraph break only when a new block starts (#353).
        # ``None`` before the first thinking event so the very first
        # chunk does not get a leading separator.
        previous_thinking_block_index: int | None = None
        # Block-transition tracking (#288). ``previous_block_kind`` is the
        # kind of the most-recent block-emitting event (``"tools"`` /
        # ``"thinking"``). When the incoming event's kind differs from the
        # previous one (and we've already emitted at least one block), the
        # active block is finalized — its last state stays in chat — and
        # we open a new message for the incoming block so the chat reads
        # as the natural ``thinking → tools → thinking`` sequence instead
        # of two ever-growing blobs.
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
        progress_state: ProgressState = ProgressState.INITIAL
        # Re-paint the placeholder defensively. The caller (bot.py) creates
        # it with the same text, so Telegram returns "message not modified"
        # which ``safe_edit_html`` silently swallows. This keeps deliver()
        # self-sufficient if the placeholder is ever opened with a different
        # text (e.g. a future caller, tests).
        await safe_edit_html(bot, chat_id, message_id, render_initial())

        async for event in stream:
            etype = event.get("type")

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

            if etype == "tool_result":
                tool_trace, chars_since_edit, last_edit_at = await handle_tool_result(
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
                chunk: str = event.get("content", "")
                answer_text += chunk
                # Content-preview: when the placeholder hasn't yet been
                # consumed by a tool or thinking block, edit it to show
                # the assistant's emerging answer (truncated, italic).
                # Debounced by the same chars/time budget as text edits
                # so we don't hammer Telegram's rate limit.
                # Skipped in draft mode — the animated draft already
                # shows the streaming answer.
                if first_block_kind is None and chunk and draft_state is None:
                    preview_now = asyncio.get_event_loop().time()
                    if progress_state == ProgressState.INITIAL:
                        progress_state = ProgressState.WORKING
                        await safe_edit_html(bot, chat_id, message_id, render_working(answer_text))
                        text_last_edit_at = preview_now
                        text_chars_since_edit = 0
                    else:
                        text_chars_since_edit += len(chunk)
                        elapsed = preview_now - text_last_edit_at
                        if (
                            text_chars_since_edit >= _EDIT_DEBOUNCE_CHARS
                            or elapsed >= _MAX_EDIT_INTERVAL_S
                        ):
                            await safe_edit_html(
                                bot, chat_id, message_id, render_working(answer_text)
                            )
                            text_last_edit_at = preview_now
                            text_chars_since_edit = 0
                (
                    text_buffer,
                    text_message_id,
                    text_chars_since_edit,
                    text_last_edit_at,
                    rendered,
                ) = await dispatch_text_delta(
                    chunk=chunk,
                    previous_block_kind=previous_block_kind,
                    bot=bot,
                    chat_id=chat_id,
                    text_buffer=text_buffer,
                    text_message_id=text_message_id,
                    chars_since_edit=text_chars_since_edit,
                    last_edit_at=text_last_edit_at,
                    reply_to_message_id=reply_to_message_id,
                    message_thread_id=message_thread_id,
                    draft_state=draft_state,
                )
                if rendered and draft_state is None:
                    # Legacy interleaved-text path: the chunk landed in a
                    # separate Telegram message, so the placeholder is now
                    # "consumed" and the next tool/thinking block must open
                    # a fresh message.
                    first_block_kind = first_block_kind or "text"
                    previous_block_kind = "text"
                # Draft mode: rendered=True but the text went to a separate
                # ephemeral draft, NOT the placeholder. Don't update block-
                # kind tracking — leave the placeholder available for the
                # tools/thinking flow.
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

        # #306: when text was already rendered progressively into an
        # interleaved text message, skip the closing answer_text duplicate.
        # Drafts (Bot API 9.3+) are ephemeral and auto-expire — they do NOT
        # persist as a chat message, so even in draft mode we still send the
        # full answer via ``safe_send_text`` to persist the conversation.
        # Any terminal_message (error / agent_terminated) flushes regardless.
        final_text = final_reply_text(
            answer_text="" if text_message_id is not None else answer_text,
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
            text_message_id=text_message_id,
            text_buffer=text_buffer,
            final_text=final_text,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
            draft_state=draft_state,
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
    """Return a :data:`~app.core.tools.send_message.SendFn` for Telegram.

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
        An async :data:`~app.core.tools.send_message.SendFn` callback ready
        to pass to :func:`~app.core.tools.send_message.make_send_message_tool`.
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
