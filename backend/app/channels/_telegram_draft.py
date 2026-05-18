"""Draft streaming helpers for the Telegram channel (Bot API 9.3+).

Extracted from :mod:`app.channels._telegram_dispatch` to stay under the
500-line ceiling.  All draft-specific state (``DraftStreamState``,
keepalive task, ``_handle_text_delta_draft``) lives here.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

# Bot API 9.3+ draft auto-expires after 30 s; we refresh every 20 s.
_DRAFT_KEEPALIVE_INTERVAL_S = 20.0
# Stable draft_id used for the text-delta draft.  Any non-zero int works;
# we use 1 since there is at most one active text draft per turn.
_TEXT_DRAFT_ID = 1

# Debounce thresholds mirrored here so _handle_text_delta_draft doesn't
# need to import from _telegram_dispatch (would create a circular import).
_EDIT_DEBOUNCE_CHARS = 40
_MAX_EDIT_INTERVAL_S = 3.0


@dataclass
class DraftStreamState:
    """Mutable state for an active sendMessageDraft text-delta draft.

    Holds the last HTML sent to the draft so the keepalive task can
    re-send it when no new chunks have arrived in the last 20 s.
    """

    chat_id: int | str
    draft_id: int
    message_thread_id: int | None
    last_html: str = ""
    last_chunk_at: float = field(default_factory=time.monotonic)
    keepalive_task: asyncio.Task[None] | None = None

    def update(self, html: str) -> None:
        """Record the latest rendered HTML for keepalive re-sends."""
        self.last_html = html
        self.last_chunk_at = time.monotonic()


async def _run_draft_keepalive(
    bot: Bot,
    state: DraftStreamState,
) -> None:
    """Refresh the draft every ``_DRAFT_KEEPALIVE_INTERVAL_S`` seconds.

    Re-sends the current ``state.last_html`` if no new chunk has been
    recorded since the last keepalive.  Cancelled by
    :func:`finalize_turn_delivery` or its caller.
    """
    from .telegram_delivery import safe_send_draft  # noqa: PLC0415

    try:
        while True:
            await asyncio.sleep(_DRAFT_KEEPALIVE_INTERVAL_S)
            await safe_send_draft(
                bot,
                state.chat_id,
                state.draft_id,
                state.last_html,
                message_thread_id=state.message_thread_id,
            )
    except asyncio.CancelledError:
        return


async def handle_text_delta_draft(
    *,
    bot: Bot,
    text_buffer: str,
    chunk: str,
    chars_since_edit: int,
    last_edit_at: float,
    draft_state: DraftStreamState,
) -> tuple[str, None, int, float]:
    """Draft-mode inner handler for text delta events.

    Sends (or refreshes) ``sendMessageDraft`` with the latest accumulated
    text.  Debounces by the same chars/time budget as the legacy path.

    On first call, opens the draft with empty text (native "Thinking…"
    placeholder) and starts the keepalive task.

    Returns ``(text_buffer, None, chars_since_edit, last_edit_at)``
    — ``text_message_id`` is always ``None`` in draft mode.
    """
    from .telegram_delivery import safe_send_draft  # noqa: PLC0415
    from .telegram_html import md_to_telegram_html  # noqa: PLC0415

    chars_since_edit += len(chunk)
    now = asyncio.get_event_loop().time()
    elapsed = now - last_edit_at

    if chars_since_edit < _EDIT_DEBOUNCE_CHARS and elapsed < _MAX_EDIT_INTERVAL_S:
        # Not yet time to flush — open draft with empty text (native
        # "Thinking…" placeholder) on very first chunk only.
        if chars_since_edit == len(chunk):
            await safe_send_draft(
                bot,
                draft_state.chat_id,
                draft_state.draft_id,
                "",
                message_thread_id=draft_state.message_thread_id,
            )
            _ensure_keepalive(bot, draft_state)
        return text_buffer, None, chars_since_edit, last_edit_at

    rendered = md_to_telegram_html(text_buffer)
    draft_state.update(rendered)
    await safe_send_draft(
        bot,
        draft_state.chat_id,
        draft_state.draft_id,
        rendered,
        message_thread_id=draft_state.message_thread_id,
    )
    _ensure_keepalive(bot, draft_state)
    return text_buffer, None, 0, now


def _ensure_keepalive(bot: Bot, draft_state: DraftStreamState) -> None:
    """Start the keepalive task if not already running."""
    if draft_state.keepalive_task is None or draft_state.keepalive_task.done():
        draft_state.keepalive_task = asyncio.create_task(
            _run_draft_keepalive(bot, draft_state),
            name=f"telegram-draft-keepalive-{draft_state.chat_id}",
        )
