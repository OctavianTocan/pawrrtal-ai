"""Post-stream Telegram cleanup — extracted from ``_telegram_dispatch``.

Split out so ``_telegram_dispatch`` fits the project's 500-line file
budget. The function is mechanically identical to its previous form
— no behavioural changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from ._telegram_draft import DraftStreamState
from .telegram_delivery import (
    safe_delete,
    safe_edit,
    safe_edit_html,
    safe_send_text,
)

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

_EMPTY_RESPONSE_FALLBACK = "⚠️ The agent finished without producing a reply. Please try again."


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
    draft_state: DraftStreamState | None = None,
) -> None:
    """Resolve the ⏳ placeholder and send the closing reply (#288, #293, #306).

    When ``draft_state`` is set, the keepalive task is cancelled and the
    final text is persisted via ``sendMessage`` (drafts auto-expire and
    never appear in the user's message history).

    When ``text_message_id`` is set, we flush its final buffer in place
    and skip the closing ``final_text`` send so the user doesn't see the
    answer twice.
    """
    if draft_state is not None and draft_state.keepalive_task is not None:
        draft_state.keepalive_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await draft_state.keepalive_task

    if first_block_kind == "tools":
        await safe_edit_html(bot, chat_id, placeholder_message_id, tool_trace)
    elif first_block_kind in ("thinking", "text") or final_text:
        await safe_delete(bot, chat_id, placeholder_message_id)
    else:
        await safe_edit(bot, chat_id, placeholder_message_id, _EMPTY_RESPONSE_FALLBACK)
        logger.warning(
            "TELEGRAM_EMPTY_STREAM chat_id=%s message_id=%s",
            chat_id,
            placeholder_message_id,
        )

    # Prefer ``final_text`` (the caller's authoritative ``answer_text``)
    # over ``text_buffer`` when both diverge — defence in depth against
    # the #346 regression class where ``text_buffer`` lagged the live
    # accumulator. ``text_buffer`` is the fallback for callers that
    # opened an interleaved message without producing a separate
    # ``final_text`` for the closing reply.
    if text_message_id is not None and (final_text or text_buffer):
        await safe_edit(bot, chat_id, text_message_id, final_text or text_buffer)
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
