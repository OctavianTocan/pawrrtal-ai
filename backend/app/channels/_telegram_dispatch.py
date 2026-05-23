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
  placeholder + final-answer message (#288, #293, #306).

Draft streaming helpers (Workstream 1) live in
:mod:`app.channels._telegram_draft`.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.providers.base import StreamEvent

from ._telegram_draft import (
    _TEXT_DRAFT_ID,
    DraftStreamState,
    handle_text_delta_draft,
)
from ._telegram_finalize import finalize_turn_delivery
from .telegram_delivery import (
    format_tool_use,
    safe_edit,
    safe_edit_html,
    safe_send_html,
    safe_send_text,
    thinking_html,
)
from .telegram_progress import (
    render_tool_error,
    render_tool_success,
    render_tools_in_flight,
)

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

# Re-export for callers that import directly from this module.
__all__ = [
    "_TEXT_DRAFT_ID",
    "DraftStreamState",
    "ToolLineState",
    "capture_terminal_event",
    "dispatch_text_delta",
    "finalize_turn_delivery",
    "handle_text_delta",
    "handle_thinking",
    "handle_tool_result",
    "handle_tool_use",
    "prepare_thinking_block",
    "prepare_tools_block",
]

# Mirror constants from ``telegram.py`` rather than import them, so the
# module can be safely imported in either direction.
_EDIT_DEBOUNCE_CHARS = 40
_MAX_EDIT_INTERVAL_S = 3.0
_EMPTY_RESPONSE_FALLBACK = "⚠️ The agent finished without producing a reply. Please try again."


# ---------------------------------------------------------------------------
# Per-tool state tracking (Workstream 4)
# ---------------------------------------------------------------------------


@dataclass
class ToolLineState:
    """State for a single tool call line in the tools-trace message.

    Tracks display text and timing so we can mutate from in-flight
    → success/failure once the ``tool_result`` event arrives.
    """

    call_id: str
    display: str
    """Formatted display string (icon + label) for the in-flight state."""
    started_at: float = field(default_factory=time.monotonic)
    result_line: str | None = None
    """Set to the rendered success/error HTML when the result arrives."""

    @property
    def rendered_line(self) -> str:
        """Current display line — result if available, else in-flight."""
        if self.result_line is not None:
            return self.result_line
        return self.display


def _render_tools_block(
    tool_states: dict[str, ToolLineState],
    in_flight_names: list[str],
) -> str:
    """Render the full tools trace from per-tool state.

    In-flight tools appear in the summary header (HTML-escaped).
    Completed tools appear as their success/error line below.  We
    deliberately do NOT also list in-flight tools as raw display lines
    in the body — that would (a) duplicate the header, and (b) leak
    unescaped ``display`` text into Telegram's HTML parser.
    """
    lines = [s.result_line for s in tool_states.values() if s.result_line is not None]
    if in_flight_names:
        header = render_tools_in_flight(in_flight_names)
        lines = [header, *lines]
    return "\n".join(lines)


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
        render_tools_in_flight([]),
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
    tool_states: dict[str, ToolLineState] | None = None,
) -> tuple[str, int, float]:
    """Inject a detailed tool-call row into the editable Telegram trace.

    When ``tool_states`` is provided (Workstream 4), the per-tool state
    dict is updated so downstream ``tool_result`` events can update the
    line in-place.

    Returns the updated ``(tool_trace, chars_since_edit, last_edit_at)``
    triple.
    """
    call_id = str(event.get("tool_use_id") or "")
    line = format_tool_use(event)

    # Track whether this event introduces a NEW tool so we can flush
    # the trace immediately — single short tool names never reach the
    # 40-char debounce threshold otherwise.
    if tool_states is not None and call_id:
        is_new_tool = call_id not in tool_states
        tool_states[call_id] = ToolLineState(call_id=call_id, display=line)
        in_flight = [s.display for s in tool_states.values() if s.result_line is None]
        tool_trace = _render_tools_block(tool_states, in_flight)
    else:
        # Legacy / missing-call_id branch: escape the raw display string
        # before appending to the (HTML-rendered) tool_trace.
        is_new_tool = not tool_trace
        escaped_line = html_lib.escape(line)
        tool_trace = f"{tool_trace}\n{escaped_line}" if tool_trace else escaped_line

    chars_since_edit += len(line)
    now = asyncio.get_event_loop().time()
    elapsed = now - last_edit_at
    should_flush = (
        is_new_tool or chars_since_edit >= _EDIT_DEBOUNCE_CHARS or elapsed >= _MAX_EDIT_INTERVAL_S
    )
    if tool_trace and should_flush:
        await safe_edit_html(bot, chat_id, message_id, tool_trace)
        return tool_trace, 0, now
    return tool_trace, chars_since_edit, last_edit_at


async def handle_tool_result(
    *,
    event: StreamEvent,
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    tool_trace: str,
    chars_since_edit: int,
    last_edit_at: float,
    tool_states: dict[str, ToolLineState],
) -> tuple[str, int, float]:
    """Update the tool trace when a ``tool_result`` event arrives.

    Computes elapsed time from the corresponding ``tool_use`` start,
    renders the success/error line, and forces an edit.
    """
    call_id = str(event.get("tool_use_id") or "")
    state = tool_states.get(call_id)
    if state is None:
        logger.debug(
            "TELEGRAM_TOOL_RESULT_NO_STATE call_id=%s chat_id=%s",
            call_id,
            chat_id,
        )
        return tool_trace, chars_since_edit, last_edit_at

    elapsed_ms = int((time.monotonic() - state.started_at) * 1000)
    is_error = bool(event.get("is_error"))

    if is_error:
        raw_error = str(event.get("content") or "Error")
        state.result_line = render_tool_error(state.display, raw_error)
    else:
        state.result_line = render_tool_success(state.display, elapsed_ms)

    in_flight = [s.display for s in tool_states.values() if s.result_line is None]
    tool_trace = _render_tools_block(tool_states, in_flight)

    now = asyncio.get_event_loop().time()
    await safe_edit_html(bot, chat_id, message_id, tool_trace)
    return tool_trace, 0, now


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
    rendered = thinking_html(thinking_text)
    if thinking_message_id is None:
        message_id = await safe_send_html(
            bot,
            chat_id,
            rendered,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
        )
        return thinking_text, message_id
    await safe_edit_html(bot, chat_id, thinking_message_id, rendered)
    return thinking_text, thinking_message_id


def capture_terminal_event(
    event: StreamEvent,
    *,
    chat_id: int | str,
    placeholder_message_id: int,
    agent_terminated_prefix: str,
    error_prefix: str,
) -> tuple[str | None, str] | None:
    """Return ``(message, prefix)`` for a terminal event, or ``None`` otherwise."""
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
    draft_state: DraftStreamState | None = None,
) -> tuple[str, int | None, int, float, bool]:
    """Apply the #306 fresh-block reset (if needed) and stream the chunk.

    Returns the updated text-buffer state plus a ``rendered`` flag:

    * ``rendered=False`` for the legacy accumulate path — when no thinking
      or tool block has rendered yet we keep "send the final answer at
      the end" UX.
    * ``rendered=True`` when an interleaved text block was opened or edited
      OR the chunk was streamed to a Bot API 9.3+ ``sendMessageDraft``.
    """
    # Draft mode: every delta streams into the same draft regardless of
    # the previous block kind. The draft animates updates in place and is
    # persisted by ``finalize_turn_delivery`` via a separate ``sendMessage``.
    if draft_state is not None:
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
            draft_state=draft_state,
        )
        return text_buffer, text_message_id, chars_since_edit, last_edit_at, True

    # Legacy editMessageText path: only open / continue an interleaved text
    # message on a block transition. Pure-text or same-block deltas keep
    # accumulating into ``answer_text`` for the closing reply.
    if previous_block_kind in (None, "text"):
        return text_buffer, text_message_id, chars_since_edit, last_edit_at, False
    if previous_block_kind != "text":
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
        draft_state=draft_state,
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
    draft_state: DraftStreamState | None = None,
) -> tuple[str, int | None, int, float]:
    """Append ``chunk`` to the live text message — open one if needed (#306).

    When ``draft_state`` is provided (``telegram_use_draft_streaming=True``),
    chunks route through ``sendMessageDraft`` instead of ``editMessageText``.
    """
    if not chunk:
        return text_buffer, text_message_id, chars_since_edit, last_edit_at
    text_buffer = f"{text_buffer}{chunk}"

    if draft_state is not None:
        return await handle_text_delta_draft(
            bot=bot,
            text_buffer=text_buffer,
            chunk=chunk,
            chars_since_edit=chars_since_edit,
            last_edit_at=last_edit_at,
            draft_state=draft_state,
        )

    # Legacy editMessageText path.
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


# ``finalize_turn_delivery`` lives in ``_telegram_finalize`` so this
# module fits the 500-line file budget. Re-exported via ``__all__``
# above for callers that import from this module.
