"""LCM retrieval observability — explain one turn's assembled memory context.

This module is the read-only microscope on top of the LCM substrate
(``lcm_context_items`` → resolved ``chat_messages`` / ``lcm_summaries``).
It answers the question "what did the agent actually see for this
turn, and how was that produced?" without firing a model call or
mutating any compaction state.

Public API
----------
``describe_assembled_context`` — resolve the assembled context for a
                                 conversation into a structured
                                 :class:`LCMContextDebugResponse`.

The schema lives next to the resolver so the API layer (
``app.infrastructure.observability.lcm.router``) and the eval harness (``backend/tests/evals``) can
both consume the same Pydantic types without crossing the
``app.schemas`` boundary, which is already at the 500-line cap.

See issue #251.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import settings as _settings
from app.models import ChatMessage, LCMContextItem, LCMSummary, LCMSummarySource

# Length of the preview snippet recorded for each item in the debug
# response.  Wide enough for the first sentence; narrow enough to keep
# the JSON payload compact even for large conversations.
_DEBUG_PREVIEW_CHARS = 240

# Same 4-chars-per-token approximation the rest of LCM uses (see
# ``app.lcm.__init__._approx_tokens``).  Duplicated here rather
# than imported so this module does not pull in the compaction-pass
# side of the package just to read.
_CHARS_PER_TOKEN = 4

ItemKind = Literal["message", "summary"]


class LCMContextDebugItem(BaseModel):
    """One row of the assembled context, in resolved + preview-friendly form."""

    ordinal: int
    item_kind: ItemKind
    item_id: uuid.UUID
    role: str | None = None
    preview: str
    token_count: int | None = None
    summary_depth: int | None = None
    summary_kind: str | None = None
    source_count: int | None = None


class LCMSettingsSnapshot(BaseModel):
    """The LCM tuning knobs that shaped this assembly call.

    Snapshotted at request time so the debug response stays useful even
    after settings change — the panel answers "what produced this
    context" not "what is configured right now."
    """

    lcm_enabled: bool
    fresh_tail_count: int
    leaf_chunk_tokens: int
    incremental_max_depth: int


class LCMContextDebugResponse(BaseModel):
    """Full debug payload for one conversation's assembled context."""

    conversation_id: uuid.UUID
    lcm_enabled: bool
    fresh_tail_count: int
    item_count: int
    message_count: int
    summary_count: int
    estimated_tokens: int
    items: list[LCMContextDebugItem]
    settings: LCMSettingsSnapshot


def _approx_tokens(text: str) -> int:
    """Rough token estimate; mirrors :mod:`app.lcm.__init__`."""
    return max(1, len(text or "") // _CHARS_PER_TOKEN)


def _preview(text: str) -> str:
    """Trim text to the debug preview length, ellipsising overflow."""
    body = (text or "").strip().replace("\n", " ")
    if len(body) <= _DEBUG_PREVIEW_CHARS:
        return body
    return body[: _DEBUG_PREVIEW_CHARS - 1] + "…"


def _resolve_fresh_tail_count(override: int | None) -> int:
    """Resolve the fresh-tail count from the override or live settings."""
    if override is not None:
        return max(0, override)
    return max(0, _settings.lcm_fresh_tail_count)


def _settings_snapshot(fresh_tail_count: int) -> LCMSettingsSnapshot:
    """Materialise the relevant LCM settings into a Pydantic snapshot."""
    return LCMSettingsSnapshot(
        lcm_enabled=_settings.lcm_enabled,
        fresh_tail_count=fresh_tail_count,
        leaf_chunk_tokens=_settings.lcm_leaf_chunk_tokens,
        incremental_max_depth=_settings.lcm_incremental_max_depth,
    )


def _empty_response(
    conversation_id: uuid.UUID,
    fresh_tail_count: int,
) -> LCMContextDebugResponse:
    """Return the empty payload when no LCM context exists yet."""
    return LCMContextDebugResponse(
        conversation_id=conversation_id,
        lcm_enabled=_settings.lcm_enabled,
        fresh_tail_count=fresh_tail_count,
        item_count=0,
        message_count=0,
        summary_count=0,
        estimated_tokens=0,
        items=[],
        settings=_settings_snapshot(fresh_tail_count),
    )


async def _load_messages(
    session: AsyncSession,
    ids: list[uuid.UUID],
) -> dict[uuid.UUID, ChatMessage]:
    """Bulk-load ChatMessages by id."""
    if not ids:
        return {}
    result = await session.execute(select(ChatMessage).where(ChatMessage.id.in_(ids)))
    return {m.id: m for m in result.scalars().all()}


async def _load_summaries(
    session: AsyncSession,
    ids: list[uuid.UUID],
) -> dict[uuid.UUID, LCMSummary]:
    """Bulk-load LCMSummaries by id."""
    if not ids:
        return {}
    result = await session.execute(select(LCMSummary).where(LCMSummary.id.in_(ids)))
    return {s.id: s for s in result.scalars().all()}


async def _summary_source_counts(
    session: AsyncSession,
    summary_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Return ``{summary_id: source_count}`` for the supplied IDs."""
    if not summary_ids:
        return {}
    result = await session.execute(
        select(LCMSummarySource.summary_id, func.count(LCMSummarySource.id))
        .where(LCMSummarySource.summary_id.in_(summary_ids))
        .group_by(LCMSummarySource.summary_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


def _build_message_item(
    item: LCMContextItem,
    msg: ChatMessage | None,
) -> LCMContextDebugItem | None:
    """Resolve a ``message`` context item to a debug row, or drop it."""
    if msg is None:
        return None
    content = msg.content or ""
    return LCMContextDebugItem(
        ordinal=item.ordinal,
        item_kind="message",
        item_id=item.item_id,
        role=msg.role,
        preview=_preview(content),
        token_count=_approx_tokens(content),
    )


def _build_summary_item(
    item: LCMContextItem,
    summary: LCMSummary | None,
    source_count: int | None,
) -> LCMContextDebugItem | None:
    """Resolve a ``summary`` context item to a debug row, or drop it."""
    if summary is None:
        return None
    return LCMContextDebugItem(
        ordinal=item.ordinal,
        item_kind="summary",
        item_id=item.item_id,
        role=None,
        preview=_preview(summary.content or ""),
        token_count=summary.token_count or _approx_tokens(summary.content or ""),
        summary_depth=summary.depth,
        summary_kind=summary.summary_kind,
        source_count=source_count,
    )


async def describe_assembled_context(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    fresh_tail_count: int | None = None,
) -> LCMContextDebugResponse:
    """Resolve the assembled LCM context for one conversation into a debug payload.

    This mirrors the read path of :func:`app.lcm.assemble_context`
    (fresh-tail cap on raw messages, all summaries preserved) but
    surfaces structural metadata — ordinal, role, summary depth/kind,
    source count, token estimate — instead of the ``[{role, content}]``
    shape the provider receives.

    Args:
        session: Open async database session.
        conversation_id: Conversation to inspect.
        fresh_tail_count: Optional override of ``settings.lcm_fresh_tail_count``.
            Used by tests and by callers that want to preview a
            different fresh-tail window without flipping the global
            setting.

    Returns:
        A structured :class:`LCMContextDebugResponse`.  Empty when no
        ``LCMContextItem`` rows exist for the conversation.
    """
    resolved_tail = _resolve_fresh_tail_count(fresh_tail_count)

    items_result = await session.execute(
        select(LCMContextItem)
        .where(LCMContextItem.conversation_id == conversation_id)
        .order_by(LCMContextItem.ordinal.asc())
    )
    all_items = list(items_result.scalars().all())
    if not all_items:
        return _empty_response(conversation_id, resolved_tail)

    # Same selection rule as ``assemble_context``: keep every summary,
    # cap raw messages to the most-recent ``resolved_tail`` entries.
    message_quota = resolved_tail
    keep: list[LCMContextItem] = []
    for item in reversed(all_items):
        if item.item_kind == "message":
            if message_quota <= 0:
                continue
            message_quota -= 1
        keep.append(item)
    keep.reverse()

    message_ids = [i.item_id for i in keep if i.item_kind == "message"]
    summary_ids = [i.item_id for i in keep if i.item_kind == "summary"]

    messages_by_id = await _load_messages(session, message_ids)
    summaries_by_id = await _load_summaries(session, summary_ids)
    source_counts = await _summary_source_counts(session, summary_ids)

    debug_items: list[LCMContextDebugItem] = []
    for item in keep:
        if item.item_kind == "message":
            row = _build_message_item(item, messages_by_id.get(item.item_id))
        else:
            row = _build_summary_item(
                item,
                summaries_by_id.get(item.item_id),
                source_counts.get(item.item_id),
            )
        if row is not None:
            debug_items.append(row)

    message_count = sum(1 for r in debug_items if r.item_kind == "message")
    summary_count = sum(1 for r in debug_items if r.item_kind == "summary")
    estimated_tokens = sum(r.token_count or 0 for r in debug_items)

    return LCMContextDebugResponse(
        conversation_id=conversation_id,
        lcm_enabled=_settings.lcm_enabled,
        fresh_tail_count=resolved_tail,
        item_count=len(debug_items),
        message_count=message_count,
        summary_count=summary_count,
        estimated_tokens=estimated_tokens,
        items=debug_items,
        settings=_settings_snapshot(resolved_tail),
    )
