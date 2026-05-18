"""TelegramChannel — progressive message-edit delivery via aiogram.

Unlike SSEChannel, which pushes bytes to an HTTP transport, TelegramChannel
delivers by calling ``bot.edit_message_text`` as chunks arrive.  There is no
byte stream to return — delivery is entirely a side-effect.  The method is
still typed as ``AsyncIterator[bytes]`` (the Channel protocol's common
denominator) and simply yields nothing.

Delivery contract
-----------------
The caller (bot.py's ``_on_message`` dispatcher function) is responsible for:

1. Sending the initial placeholder message (``"⏳"``) and capturing its
   ``message_id``.
2. Building a ``ChannelMessage`` with the following ``metadata`` keys:

   - ``bot``: the live ``aiogram.Bot`` instance.
   - ``chat_id``: Telegram chat ID (int or str).
   - ``message_id``: ID of the placeholder message to edit progressively.

3. Calling ``channel.deliver(provider.stream(...), channel_msg)`` and
   consuming the resulting async iterator to drive delivery:
   ``async for _ in channel.deliver(...): pass``.

Debounce
--------
Telegram's flood control allows roughly 20 edits per minute per chat (one
every ~3 seconds).  We debounce by *character growth*: an edit is sent when
either ``_EDIT_DEBOUNCE_CHARS`` new characters have accumulated **or**
``_MAX_EDIT_INTERVAL`` seconds have elapsed since the last edit.  A final
edit is always sent after the stream ends to ensure the user sees the
complete text.

Non-text outcomes
-----------------
The stream may end without ever emitting a ``delta`` (e.g. the agent loop's
safety layer tripped ``max_iterations`` because the model looped on tool
calls, or the provider raised). In those cases the placeholder ⏳ would
otherwise sit forever — the user has no signal the turn ended. To prevent
that, the channel watches for two structured terminal events and reports
them in-chat:

- ``agent_terminated`` → placeholder is replaced with the loop's human copy
  prefixed by ``⚠️``.
- ``error`` → placeholder is replaced with the error content prefixed by
  ``❌``.

A fallback message is shown when the turn closes without anything to say:

- The stream produced no text and no terminal event ("empty stream").
- The stream produced tool calls but no answer text and no thinking
  trace ("tool-only turn" — see #293).

Error handling
--------------
``TelegramBadRequest: message is not modified`` is swallowed — it's benign
and happens when the model emits an empty delta between two flush points.
All other errors are logged as warnings but do not raise; a partial response
visible to the user is better than a silent failure.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.providers.base import StreamEvent
from app.core.tools.send_message import SendFn

from ._telegram_dispatch import (
    finalize_turn_delivery,
    handle_thinking,
    handle_tool_use,
    prepare_thinking_block,
    prepare_tools_block,
)
from .base import ChannelMessage
from .telegram_delivery import (
    final_reply_text,
    optional_int,
    routing_kwargs,
)
from .telegram_html import md_to_telegram_html

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

    async def deliver(
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
        # ``tool_message_id`` starts as the placeholder so the FIRST tools
        # block consumes the ⏳; on a thinking→tools transition (issue #288)
        # we open a fresh Telegram message for the new tools block and
        # rebind this slot so subsequent edits land there.
        tool_message_id: int = message_id
        answer_text = ""
        thinking_text = ""
        thinking_message_id: int | None = None
        chars_since_edit = 0
        last_edit_at = asyncio.get_event_loop().time()
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

        async for event in stream:
            etype = event.get("type")

            if etype == "tool_use":
                first_block_kind = first_block_kind or "tools"
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
                )
                continue

            if etype == "thinking":
                first_block_kind = first_block_kind or "thinking"
                thinking_text, thinking_message_id = prepare_thinking_block(
                    previous_block_kind=previous_block_kind,
                    thinking_text=thinking_text,
                    thinking_message_id=thinking_message_id,
                )
                previous_block_kind = "thinking"
                thinking_text, thinking_message_id = await handle_thinking(
                    event=event,
                    bot=bot,
                    chat_id=chat_id,
                    thinking_text=thinking_text,
                    thinking_message_id=thinking_message_id,
                    reply_to_message_id=reply_to_message_id,
                    message_thread_id=message_thread_id,
                )
                continue

            if etype == "delta":
                chunk: str = event.get("content", "")
                answer_text += chunk
                continue

            if etype == "agent_terminated":
                # Safety layer tripped (max_iterations, consecutive_tool_errors,
                # wall_clock).  Keep the human-readable copy so the user sees
                # *why* the turn ended instead of an eternal ⏳.
                terminal_message = event.get("content", "Agent terminated.")
                terminal_prefix = _AGENT_TERMINATED_PREFIX
                logger.warning(
                    "TELEGRAM_AGENT_TERMINATED chat_id=%s message_id=%s message=%s",
                    chat_id,
                    message_id,
                    terminal_message,
                )
                continue

            if etype == "error":
                terminal_message = event.get("content", "Unknown error.")
                terminal_prefix = _ERROR_PREFIX
                logger.warning(
                    "TELEGRAM_STREAM_ERROR chat_id=%s message_id=%s message=%s",
                    chat_id,
                    message_id,
                    terminal_message,
                )
                continue

        final_text = final_reply_text(
            answer_text=answer_text,
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
            final_text=final_text,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
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
