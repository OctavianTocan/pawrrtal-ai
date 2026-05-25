"""Post-stream Telegram cleanup — extracted from ``_telegram_dispatch``.

Split out so ``_telegram_dispatch`` fits the project's 500-line file
budget. The function is mechanically identical to its previous form
— no behavioural changes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .telegram_delivery import (
    safe_delete,
    safe_edit,
    safe_edit_html,
    safe_send_text,
    thinking_html,
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
    reply_markup: Any | None = None,
) -> None:
    """Resolve the ⏳ placeholder and send the closing reply (#288, #293, #306).

    When ``text_message_id`` is set, we flush its final buffer in place
    and skip the closing ``final_text`` send so the user doesn't see the
    answer twice.

    ``reply_markup`` (#368) attaches an inline keyboard to the closing
    reply when one is supplied — the regenerate button is the only
    current caller. The markup rides on whichever message the user
    ultimately sees as the final answer; in the interleaved-text path
    that's the existing ``text_message_id`` edit, otherwise it's the
    closing ``safe_send_text``.
    """
    if first_block_kind == "tools":
        await safe_edit_html(bot, chat_id, placeholder_message_id, tool_trace)
    elif first_block_kind == "thinking":
        await safe_edit_html(bot, chat_id, placeholder_message_id, thinking_html(thinking_text))
    elif first_block_kind == "text" or final_text:
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
        # Interleaved-text path: the answer already lives in an
        # in-place edited message. We don't re-edit the text just to
        # attach a markup — Telegram requires editMessageReplyMarkup
        # for that, which would double the API spend. For now we just
        # send a tiny zero-content trailing message that carries the
        # button, so the user still has the affordance. The trailing
        # message is empty when no markup is supplied.
        await safe_edit(bot, chat_id, text_message_id, final_text or text_buffer)
        if reply_markup is not None:
            await _send_regenerate_tail(
                bot=bot,
                chat_id=chat_id,
                reply_to_message_id=reply_to_message_id,
                message_thread_id=message_thread_id,
                reply_markup=reply_markup,
            )
        return

    if final_text:
        await safe_send_text(
            bot,
            chat_id,
            final_text,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
            reply_markup=reply_markup,
        )
        return

    if previous_block_kind == "tools" and not thinking_text:
        await safe_send_text(
            bot,
            chat_id,
            _EMPTY_RESPONSE_FALLBACK,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
            reply_markup=reply_markup,
        )
        logger.warning(
            "TELEGRAM_TOOL_ONLY_TURN chat_id=%s message_id=%s tool_trace_len=%d",
            chat_id,
            placeholder_message_id,
            len(tool_trace),
        )


# Telegram requires `text` on send_message; a single whitespace
# character is the smallest payload that lets us attach a button
# below an already-rendered interleaved-text reply without re-editing
# the answer message itself.
_REGENERATE_TAIL_TEXT = "·"


async def _send_regenerate_tail(
    *,
    bot: Bot,
    chat_id: int | str,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
    reply_markup: Any,
) -> None:
    """Post a minimal trailing message that carries the regenerate button.

    Used only on the interleaved-text path (#306) where the final
    answer was rendered into an in-place-edited Telegram message.
    Re-editing that message with a markup would require a separate
    ``editMessageReplyMarkup`` call; sending one tiny extra message
    keeps the helper symmetric with the closing-send path.
    """
    await safe_send_text(
        bot,
        chat_id,
        _REGENERATE_TAIL_TEXT,
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
        reply_markup=reply_markup,
    )
