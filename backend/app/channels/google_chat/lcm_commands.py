"""LCM commands for the Google Chat channel — ``/lcm`` status + ``/compact``.

Thin channel-local wrappers over the shared LCM services
(:func:`app.lcm.compact_leaf_if_needed` under
:func:`app.lcm.background.acquire_lcm_lock`) plus a compact status read over
the ``LCMSummary`` / ``LCMContextItem`` tables. Mirrors
:mod:`app.channels.telegram.lcm_status` / ``compact_command``, returning plain
text the ingress posts back as a Chat message.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import settings
from app.infrastructure.database.legacy import async_session_maker
from app.infrastructure.models.lcm import LCMContextItem, LCMSummary
from app.lcm import compact_leaf_if_needed
from app.lcm.background import acquire_lcm_lock
from app.providers.model_id import InvalidModelId

_LCM_DISABLED = "🧠 LCM is disabled (`settings.lcm_enabled = False`)."
_MESSAGE_KIND = "message"
_SUMMARY_KIND = "summary"


async def lcm_status_text(*, conversation_id: uuid.UUID, session: AsyncSession) -> str:
    """Return a compact LCM-status block for *conversation_id*."""
    if not settings.lcm_enabled:
        return _LCM_DISABLED
    by_kind = await _count_context_items_by_kind(session, conversation_id)
    messages = by_kind.get(_MESSAGE_KIND, 0)
    summaries = by_kind.get(_SUMMARY_KIND, 0)
    items = sum(by_kind.values())  # total of all kinds, robust to a future 3rd kind
    summary_nodes = await _count_summary_nodes(session, conversation_id)
    return (
        "🧠 *LCM status*\n"
        f"• Context items: {items} ({messages} messages, {summaries} compacted)\n"
        f"• Summary nodes: {summary_nodes}"
    )


async def run_compaction(*, conversation_id: uuid.UUID, user_id: uuid.UUID, model_id: str) -> str:
    """Force one leaf-compaction pass under the LCM lock; return the outcome."""
    if not settings.lcm_enabled:
        return _LCM_DISABLED
    try:
        async with acquire_lcm_lock(conversation_id), async_session_maker() as session:
            compacted = await compact_leaf_if_needed(
                session,
                conversation_id=conversation_id,
                user_id=user_id,
                model_id=model_id,
                fresh_tail_count=settings.lcm_fresh_tail_count,
                max_chunk_tokens=settings.lcm_leaf_chunk_tokens,
            )
    except (OSError, RuntimeError, TimeoutError, SQLAlchemyError, InvalidModelId) as exc:
        return f"❌ Compaction failed: `{type(exc).__name__}`. Check the backend log."
    if compacted:
        return "🧠 *Compact*\n✅ Compacted the oldest eligible messages into a new summary."
    return f"🧠 *Compact*\n💤 Nothing to compact yet (need more than {settings.lcm_fresh_tail_count} items)."


async def _count_context_items_by_kind(
    session: AsyncSession, conversation_id: uuid.UUID
) -> dict[str, int]:
    """Return ``{item_kind: count}`` for the conversation's context items (one query)."""
    stmt = (
        select(LCMContextItem.item_kind, func.count())
        .where(LCMContextItem.conversation_id == conversation_id)
        .group_by(LCMContextItem.item_kind)
    )
    rows = await session.execute(stmt)
    return {str(kind): int(count) for kind, count in rows.all()}


async def _count_summary_nodes(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    """Count the conversation's LCM summary nodes (full history, all depths)."""
    stmt = select(func.count()).where(LCMSummary.conversation_id == conversation_id)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)
