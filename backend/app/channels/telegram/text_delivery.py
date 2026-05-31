"""Text-delta delivery helpers for Telegram channel turns."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.providers.base import StreamEvent

from .delivery import safe_edit_html
from .dispatch import dispatch_text_delta
from .progress import ProgressState, render_working

if TYPE_CHECKING:
    from aiogram import Bot

EDIT_DEBOUNCE_CHARS = 40
MAX_EDIT_INTERVAL_S = 3.0


@dataclass
class TextDeliveryState:
    """Mutable state for one Telegram text block."""

    answer_text: str = ""
    buffer: str = ""
    message_id: int | None = None
    chars_since_edit: int = 0
    last_edit_at: float = 0.0
    progress_state: ProgressState = ProgressState.INITIAL


async def handle_delta_event(
    *,
    event: StreamEvent,
    bot: Bot,
    chat_id: int | str,
    placeholder_message_id: int,
    text_state: TextDeliveryState,
    first_block_kind: str | None,
    previous_block_kind: str | None,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> bool:
    """Apply one text delta and return whether it rendered as its own block."""
    chunk: str = event.get("content", "")
    text_state.answer_text += chunk
    if first_block_kind is None and chunk:
        await _update_placeholder_preview(
            bot=bot,
            chat_id=chat_id,
            message_id=placeholder_message_id,
            chunk=chunk,
            text_state=text_state,
        )
    (
        text_state.buffer,
        text_state.message_id,
        text_state.chars_since_edit,
        text_state.last_edit_at,
        rendered,
    ) = await dispatch_text_delta(
        chunk=chunk,
        previous_block_kind=previous_block_kind,
        bot=bot,
        chat_id=chat_id,
        text_buffer=text_state.buffer,
        text_message_id=text_state.message_id,
        chars_since_edit=text_state.chars_since_edit,
        last_edit_at=text_state.last_edit_at,
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
    )
    return rendered


async def _update_placeholder_preview(
    *,
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    chunk: str,
    text_state: TextDeliveryState,
) -> None:
    """Edit the initial placeholder with the emerging answer preview."""
    preview_now = asyncio.get_event_loop().time()
    if text_state.progress_state == ProgressState.INITIAL:
        text_state.progress_state = ProgressState.WORKING
        await safe_edit_html(bot, chat_id, message_id, render_working(text_state.answer_text))
        text_state.last_edit_at = preview_now
        text_state.chars_since_edit = 0
        return
    text_state.chars_since_edit += len(chunk)
    elapsed = preview_now - text_state.last_edit_at
    if text_state.chars_since_edit < EDIT_DEBOUNCE_CHARS and elapsed < MAX_EDIT_INTERVAL_S:
        return
    await safe_edit_html(bot, chat_id, message_id, render_working(text_state.answer_text))
    text_state.last_edit_at = preview_now
    text_state.chars_since_edit = 0
