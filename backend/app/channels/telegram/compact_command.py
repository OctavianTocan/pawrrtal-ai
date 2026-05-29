"""``/compact`` command for the Telegram channel.

Forces an LCM leaf-compaction pass on the caller's current
conversation. Distinct from the background trigger fired after every
turn (``app.core.lcm.background.schedule_lcm_compaction``) in two ways:

1. **Synchronous.** Calls :func:`compact_leaf_if_needed` directly so
   the reply reflects what actually happened on this turn — number of
   rows compacted, "nothing to compact", or the error class. The
   background helper swallows errors silently, which is the right
   default for routine ops but useless when the operator pulls the
   trigger themselves.
2. **No lock contention.** Reuses the same per-conversation lock as
   the background path so a manual /compact and a freshly-scheduled
   background pass don't race on the
   ``(conversation_id, ordinal)`` unique constraint in
   ``lcm_context_items``.

Stays under the 500-line budget; pure formatter + one async handler +
its own copy constants, mirroring :mod:`lcm_status` in shape.
"""

from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import (
    get_or_create_telegram_conversation_full,
    get_user_id_for_external,
)
from app.channels.telegram.model_defaults import resolve_effective_model_id
from app.core.config import settings
from app.core.lcm import compact_leaf_if_needed
from app.core.lcm.background import acquire_lcm_lock
from app.core.providers.model_id import InvalidModelId
from app.infrastructure.database.legacy import async_session_maker


class _TelegramSenderLike(Protocol):
    """Structural type for the subset of ``TelegramSender`` /compact needs."""

    @property
    def user_id(self) -> int:
        """Telegram numeric user id."""
        ...

    @property
    def chat_id(self) -> int:
        """Telegram chat id (DM or group)."""
        ...

    @property
    def thread_id(self) -> int | None:
        """Telegram topic thread id, or ``None`` outside a topic."""
        ...


logger = logging.getLogger(__name__)

_PROVIDER = "telegram"

_NOT_BOUND_MESSAGE = "Connect your account first before running /compact."
_LCM_DISABLED_MESSAGE = (
    "🧠 Compact\n\n"
    "🛑 LCM is disabled (settings.lcm_enabled = False).\n"
    "Memory compaction is not running for any conversation."
)
_COMPACTED_MESSAGE = "🧠 Compact\n\n✅ Compacted oldest eligible messages into a new summary."
_NOTHING_TO_COMPACT_MESSAGE = (
    "🧠 Compact\n\n💤 Nothing to compact yet (need more than {fresh_tail_count} items)."
)
_ERROR_MESSAGE = (
    "🧠 Compact\n\n❌ Compaction failed: <code>{error_class}</code>\n"
    "Check the backend log for details (LCM_COMPACT_BG_ERR-style trace)."
)


async def handle_compact_command(
    *,
    sender: _TelegramSenderLike,
    session: AsyncSession,
) -> str:
    """Run one synchronous LCM leaf-compaction pass; reply with the result.

    Args:
        sender: Normalized sender identity.
        session: Async DB session used only for the user / conversation
            lookups; the compaction itself runs against a fresh session
            opened by :func:`async_session_maker` so it can commit
            independently of the request lifecycle (mirrors the
            background helper).

    Returns:
        Reply string the bot should send immediately.
    """
    if not settings.lcm_enabled:
        return _LCM_DISABLED_MESSAGE

    pawrrtal_user_id = await get_user_id_for_external(
        provider=_PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if pawrrtal_user_id is None:
        return _NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )

    # Default the summary model to whatever the conversation is using
    # (matches the fallback in ``compact_leaf_if_needed`` when
    # ``lcm_summary_model`` is unset). Honours the user's pinned default
    # before falling back to the catalog default — see
    # :func:`resolve_effective_model_id`.
    summary_model_id = await resolve_effective_model_id(
        session=session,
        user_id=pawrrtal_user_id,
        conversation_model_id=conversation.model_id,
    )

    # Take the per-conversation lock to serialize against any
    # background pass that turn_runner.py just scheduled — both paths
    # mutate the ``(conversation_id, ordinal)`` slot so they must not
    # interleave.
    async with acquire_lcm_lock(conversation.id):
        try:
            async with async_session_maker() as compact_session:
                ran = await compact_leaf_if_needed(
                    compact_session,
                    conversation_id=conversation.id,
                    user_id=pawrrtal_user_id,
                    model_id=summary_model_id,
                    fresh_tail_count=settings.lcm_fresh_tail_count,
                    max_chunk_tokens=settings.lcm_leaf_chunk_tokens,
                )
                await compact_session.commit()
        except (OSError, RuntimeError, TimeoutError, SQLAlchemyError, InvalidModelId) as exc:
            logger.exception(
                "TELEGRAM_COMPACT_ERR conversation_id=%s",
                conversation.id,
            )
            return _ERROR_MESSAGE.format(error_class=type(exc).__name__)

    if not ran:
        return _NOTHING_TO_COMPACT_MESSAGE.format(fresh_tail_count=settings.lcm_fresh_tail_count)
    return _COMPACTED_MESSAGE
