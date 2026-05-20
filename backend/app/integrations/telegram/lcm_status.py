"""``/lcm`` command for the Telegram channel.

Surfaces Lossless Context Management state for the current conversation
so the operator can diagnose memory regressions from Telegram without
SSH'ing into the server. Closes #303.

Mirrors :mod:`app.integrations.telegram.status` in shape: pure
formatter + one async handler + its own copy constants. Stays under
the 500-line budget.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.channel import (
    get_or_create_telegram_conversation_full,
    get_user_id_for_external,
)
from app.models import LCMContextItem, LCMSummary


class _TelegramSenderLike(Protocol):
    """Structural type for the subset of ``TelegramSender`` /lcm needs.

    Same shape as :class:`app.integrations.telegram.status._TelegramSenderLike`
    — declared independently here so the two modules don't import each
    other (sentrux's ``max_cycles=0`` forbids it).
    """

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

_LCM_NOT_BOUND_MESSAGE = "Connect your account first before asking for LCM status."
_LCM_NO_CONVERSATION_MESSAGE = (
    "🧠 LCM status\n\n💬 No conversation yet — send a message to start one."
)
_LCM_DISABLED_MESSAGE = (
    "🧠 LCM status\n\n"
    "🛑 LCM is disabled (settings.lcm_enabled = False).\n"
    "Memory compaction is not running for any conversation."
)
_LCM_HEADER = (
    "🧠 LCM status\n\n"
    "✅ LCM enabled\n"
    "💬 Conversation: <code>{conversation_id}</code>\n\n"
    "📦 Context items (assembled view)\n"
    "   • Total: {item_total}\n"
    "   • Raw messages: {item_messages}\n"
    "   • Compacted summaries: {item_summaries}\n\n"
    "🗂  Summary nodes (full history)\n"
    "   • Total: {summary_total}{summary_breakdown}{latest_block}"
)
_LCM_LATEST_BLOCK = (
    "\n\n🕒 Most recent summary\n"
    "   • Depth: {depth} ({depth_label})\n"
    "   • Kind: {kind}\n"
    "   • Tokens: {tokens}\n"
    "   • Created: {created_ago} ago"
)

# Granularity constants for the relative-time renderer below.
_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3_600
_SECONDS_PER_DAY = 86_400


def _format_duration(seconds: float) -> str:
    """Render a positive duration as ``"3d 1h"`` / ``"4h 12m"`` / ``"34s"``."""
    total = int(max(0.0, seconds))
    days, rem = divmod(total, _SECONDS_PER_DAY)
    hours, rem = divmod(rem, _SECONDS_PER_HOUR)
    minutes, secs = divmod(rem, _SECONDS_PER_MINUTE)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _now_utc() -> datetime:
    """Indirection seam for tests that want to freeze 'now'."""
    return datetime.now(UTC)


def _depth_label(depth: int) -> str:
    """Return ``"leaf"`` for depth 0, ``"condensed L<depth>"`` otherwise."""
    if depth <= 0:
        return "leaf"
    return f"condensed L{depth}"


def _render_breakdown(rows: Sequence[tuple[int, str, int]]) -> str:
    """Format ``[(depth, kind, count)]`` rows into a Markdown sub-list.

    Returns an empty string for an empty input so the caller's f-string
    drops the section cleanly.
    """
    if not rows:
        return ""
    parts = [f"\n   • Depth {depth} ({kind}): {count}" for depth, kind, count in sorted(rows)]
    return "".join(parts)


async def _query_summary_counts(
    session: AsyncSession, conversation_id: object
) -> list[tuple[int, str, int]]:
    """Return summary-count rows grouped by ``(depth, summary_kind)``."""
    stmt = (
        select(LCMSummary.depth, LCMSummary.summary_kind, func.count())
        .where(LCMSummary.conversation_id == conversation_id)
        .group_by(LCMSummary.depth, LCMSummary.summary_kind)
    )
    rows = await session.execute(stmt)
    return [(row.depth, row.summary_kind, row[2]) for row in rows]


async def _query_context_item_counts(
    session: AsyncSession, conversation_id: object
) -> dict[str, int]:
    """Return ``{item_kind: count}`` over ``lcm_context_items`` for *conversation_id*."""
    stmt = (
        select(LCMContextItem.item_kind, func.count())
        .where(LCMContextItem.conversation_id == conversation_id)
        .group_by(LCMContextItem.item_kind)
    )
    rows = await session.execute(stmt)
    return {row[0]: row[1] for row in rows}


async def _query_latest_summary(
    session: AsyncSession, conversation_id: object
) -> LCMSummary | None:
    """Return the most recently created ``LCMSummary`` for *conversation_id*."""
    stmt = (
        select(LCMSummary)
        .where(LCMSummary.conversation_id == conversation_id)
        .order_by(LCMSummary.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _render_lcm_status_message(
    *,
    conversation_id: object,
    summary_rows: Sequence[tuple[int, str, int]],
    item_counts: dict[str, int],
    latest: LCMSummary | None,
    now: datetime,
) -> str:
    """Pure formatter — used by tests + the live handler."""
    item_messages = int(item_counts.get("message", 0))
    item_summaries = int(item_counts.get("summary", 0))
    item_total = item_messages + item_summaries
    summary_total = sum(count for *_unused, count in summary_rows)
    breakdown = _render_breakdown(summary_rows)
    latest_block = ""
    if latest is not None:
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        latest_block = _LCM_LATEST_BLOCK.format(
            depth=latest.depth,
            depth_label=_depth_label(latest.depth),
            kind=latest.summary_kind,
            tokens=latest.token_count,
            created_ago=_format_duration((now - created_at).total_seconds()),
        )
    return _LCM_HEADER.format(
        conversation_id=conversation_id,
        item_total=item_total,
        item_messages=item_messages,
        item_summaries=item_summaries,
        summary_total=summary_total,
        summary_breakdown=breakdown,
        latest_block=latest_block,
    )


async def handle_lcm_command(
    *,
    sender: _TelegramSenderLike,
    session: AsyncSession,
) -> str:
    """Render the LCM status reply for ``/lcm``.

    Returns a static "LCM disabled" reply when ``settings.lcm_enabled``
    is False so the operator can immediately tell the system isn't
    compacting anything.  When enabled, queries the same tables LCM
    writes during ingest + compaction and renders a concise summary.

    Closes #303.
    """
    if not settings.lcm_enabled:
        return _LCM_DISABLED_MESSAGE

    pawrrtal_user_id = await get_user_id_for_external(
        provider=_PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if pawrrtal_user_id is None:
        return _LCM_NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )

    summary_rows = await _query_summary_counts(session, conversation.id)
    item_counts = await _query_context_item_counts(session, conversation.id)
    latest = await _query_latest_summary(session, conversation.id)

    if not summary_rows and not item_counts:
        return _LCM_NO_CONVERSATION_MESSAGE

    return _render_lcm_status_message(
        conversation_id=conversation.id,
        summary_rows=summary_rows,
        item_counts=item_counts,
        latest=latest,
        now=_now_utc(),
    )
