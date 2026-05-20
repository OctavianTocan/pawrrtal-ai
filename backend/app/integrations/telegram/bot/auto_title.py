"""Auto-title helpers for Telegram conversations.

Derives a short title from the user's first message, persists it on the
``Conversation`` row, and (when the chat lives in a topic thread) renames
the Telegram topic to match. Fires once per conversation — gated by
``title_set_by IS NULL``.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.db import async_session_maker

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

DEFAULT_MAX_TITLE_LENGTH = 48
"""Max characters for an auto-derived title before we truncate with an ellipsis."""


def generate_title(text: str, max_len: int = DEFAULT_MAX_TITLE_LENGTH) -> str:
    """Derive a short title from the first user message.

    Strips leading slash-command prefixes (e.g. leftovers from ``/new``),
    truncates to *max_len* characters, appends an ellipsis when truncated,
    and falls back to ``"Telegram"`` for empty input.
    """
    cleaned = text.strip()
    # Strip a leading /command (shouldn't normally reach here, but belt-and-
    # suspenders: the user might type "/new hello" as their first message).
    if cleaned.startswith("/"):
        # Keep everything after the first word (the command itself).
        cleaned = cleaned.split(None, 1)[1] if " " in cleaned else ""
    cleaned = cleaned.strip()
    if not cleaned:
        return "Telegram"
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


async def maybe_set_auto_title(
    *,
    bot: Bot,
    conversation_id: uuid.UUID,
    user_text: str,
    chat_id: int,
    thread_id: int | None,
) -> None:
    """Generate and persist an auto-title for a conversation's first turn.

    Fires once only — gated by ``title_set_by IS NULL``.  On success sets
    ``title_set_by = 'auto'`` so the gate is never tripped again for this
    conversation.  If the conversation lives in a Telegram topic thread,
    also calls ``editForumTopic`` to rename the thread to match, giving
    users a readable label in their Telegram topic list.

    Args:
        bot: Live aiogram ``Bot`` instance.
        conversation_id: UUID of the conversation to maybe-title.
        user_text: The user's first message — used to derive the title.
        chat_id: Telegram chat ID (needed for ``editForumTopic``).
        thread_id: Telegram topic thread ID, or ``None`` for plain DMs.
    """
    async with async_session_maker() as session:
        from app.models import Conversation  # noqa: PLC0415

        conv = await session.get(Conversation, conversation_id)
        if conv is None or conv.title_set_by is not None:
            return  # already titled — nothing to do

        title = generate_title(user_text)
        conv.title = title
        conv.title_set_by = "auto"
        await session.commit()

    logger.info(
        "TELEGRAM_AUTO_TITLE conversation_id=%s title=%r thread_id=%s",
        conversation_id,
        title,
        thread_id,
    )

    # Rename the Telegram topic thread so the user sees the derived title
    # in their Topics list.  Only possible when the chat has topics enabled
    # and the bot has the necessary admin rights — errors are logged as
    # warnings and swallowed so the feature degrades gracefully.
    if thread_id is not None:
        try:
            await bot.edit_forum_topic(
                chat_id=chat_id,
                message_thread_id=thread_id,
                name=title,
            )
        except Exception as exc:
            logger.warning(
                "TELEGRAM_EDIT_TOPIC_FAILED chat_id=%s thread_id=%s error=%s",
                chat_id,
                thread_id,
                exc,
            )
