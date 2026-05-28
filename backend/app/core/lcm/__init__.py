"""Lossless Context Management — ingest, assembly, and leaf compaction.

Public API
----------
``ingest_message``         — record a new ChatMessage in lcm_context_items
``assemble_context``       — build the [{role, content}] context list for a turn
``compact_leaf_if_needed`` — summarise the oldest non-fresh items into a leaf
                             LCMSummary and rewrite lcm_context_items in place

All functions are always importable; callers gate on ``settings.lcm_enabled``
(default ``False``) before invoking them.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as settings
from app.core.lcm.condense import run_condensation_cascade
from app.core.providers import resolve_llm
from app.models import ChatMessage, LCMContextItem, LCMSummary, LCMSummarySource

_log = logging.getLogger(__name__)

# Character cap for the deterministic-truncation fallback when both the
# normal and aggressive provider summarisations fail or return empty
# text.  Tuned to roughly 375 tokens (4 chars ≈ 1 token), small enough
# to keep the assembled context tight while still leaving the model
# enough surface to recover continuity.
_FALLBACK_TRUNCATE_CHARS = 1500


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def ingest_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
) -> LCMContextItem:
    """Append a ChatMessage to the conversation's ``lcm_context_items`` list.

    Creates one :class:`~app.models.LCMContextItem` row with
    ``item_kind="message"`` at the next free ordinal slot
    (``max(ordinal) + 1`` for the conversation, or ``0`` for the very first
    message).

    The caller must commit the session after this call; the function calls
    ``session.flush()`` so the new row's ``id`` is populated before returning.
    """
    result = await session.execute(
        select(func.max(LCMContextItem.ordinal)).where(
            LCMContextItem.conversation_id == conversation_id
        )
    )
    current_max = result.scalar()
    next_ordinal = 0 if current_max is None else current_max + 1

    item = LCMContextItem(
        conversation_id=conversation_id,
        ordinal=next_ordinal,
        item_kind="message",
        item_id=message_id,
    )
    session.add(item)
    await session.flush()
    return item


async def _ensure_lcm_context_items_backfilled(
    session: AsyncSession,
    conversation_id: uuid.UUID,
) -> list[LCMContextItem]:
    """Ensure that LCMContextItems are backfilled from ChatMessages if empty."""
    result = await session.execute(
        select(LCMContextItem)
        .where(LCMContextItem.conversation_id == conversation_id)
        .order_by(LCMContextItem.ordinal.asc())
    )
    all_items = list(result.scalars().all())
    if all_items:
        return all_items

    # If empty, check if ChatMessages exist and backfill them
    msg_result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.ordinal.asc())
    )
    messages = list(msg_result.scalars().all())
    if not messages:
        return []

    _log.info(
        "LCM_BACKFILL_START conversation_id=%s messages=%d",
        conversation_id,
        len(messages),
    )
    backfilled_items = []
    for idx, msg in enumerate(messages):
        item = LCMContextItem(
            conversation_id=conversation_id,
            ordinal=idx,
            item_kind="message",
            item_id=msg.id,
        )
        session.add(item)
        backfilled_items.append(item)

    await session.flush()
    _log.info(
        "LCM_BACKFILL_COMPLETE conversation_id=%s items=%d",
        conversation_id,
        len(backfilled_items),
    )
    return backfilled_items


async def assemble_context(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    fresh_tail_count: int,
) -> list[dict[str, Any]]:
    """Return the assembled context window for a conversation turn.

    Implements the per-turn assembly contract from ``docs/design/lcm.md``:
    the **protected fresh tail** of the most recent raw messages (up to
    ``fresh_tail_count``) plus **every summary item** that precedes /
    interleaves them.  Summaries are *always* delivered — they are the
    only handle the model has on compacted history — and a naive
    ``ORDER BY ordinal DESC LIMIT fresh_tail_count`` over all items
    would silently drop the (older, lower-ordinal) summary rows once
    compaction has run.

    Item-kind handling:

    * ``"message"`` — resolved to its :class:`~app.models.ChatMessage`;
      only ``user`` and ``assistant`` roles are included.  Capped to
      the most-recent ``fresh_tail_count`` messages.
    * ``"summary"`` — resolved to its :class:`~app.models.LCMSummary`
      and injected as a synthetic ``user`` message with a
      ``[Summary of earlier conversation]`` prefix so both the model
      and human readers recognise it as compacted history rather than
      a real turn.  All summaries for the conversation are kept.

    Returns an empty list if no items exist yet.
    """
    all_items = await _ensure_lcm_context_items_backfilled(session, conversation_id)
    if not all_items:
        return []

    # Cap message items to the most-recent ``fresh_tail_count`` while
    # preserving every summary item.  Walking the ordinal-ordered list
    # in reverse lets us tag the eligible message tail without
    # disturbing summary ordering.
    message_tail_quota = fresh_tail_count
    keep: list[LCMContextItem] = []
    for item in reversed(all_items):
        if item.item_kind == "message":
            if message_tail_quota <= 0:
                continue
            message_tail_quota -= 1
        keep.append(item)
    keep.reverse()  # restore chronological order

    message_ids = [item.item_id for item in keep if item.item_kind == "message"]
    summary_ids = [item.item_id for item in keep if item.item_kind == "summary"]

    messages_by_id: dict[uuid.UUID, ChatMessage] = {}
    if message_ids:
        msg_result = await session.execute(
            select(ChatMessage).where(ChatMessage.id.in_(message_ids))
        )
        messages_by_id = {m.id: m for m in msg_result.scalars().all()}

    summaries_by_id: dict[uuid.UUID, LCMSummary] = {}
    if summary_ids:
        sum_result = await session.execute(select(LCMSummary).where(LCMSummary.id.in_(summary_ids)))
        summaries_by_id = {s.id: s for s in sum_result.scalars().all()}

    context: list[dict[str, Any]] = []
    for item in keep:
        turn = _assemble_item_to_turn(item, messages_by_id, summaries_by_id)
        if turn is not None:
            context.append(turn)
    return context


def _assemble_item_to_turn(
    item: LCMContextItem,
    messages_by_id: dict[uuid.UUID, ChatMessage],
    summaries_by_id: dict[uuid.UUID, LCMSummary],
) -> dict[str, Any] | None:
    """Resolve one ``LCMContextItem`` to its ``{role, content}`` shape, or drop it.

    Returns ``None`` when the backing row is missing, was a non-chat role
    (``system``, ``tool``), or carries no content — keeps
    :func:`assemble_context` flat enough to fit the project's nesting
    budget.
    """
    if item.item_kind == "message":
        msg = messages_by_id.get(item.item_id)
        if msg is None or msg.role not in {"user", "assistant"}:
            return None
        return {"role": msg.role, "content": msg.content or ""}
    if item.item_kind == "summary":
        summary = summaries_by_id.get(item.item_id)
        if summary is None:
            return None
        return {
            "role": "user",
            "content": f"[Summary of earlier conversation]\n{summary.content}",
        }
    return None


# ---------------------------------------------------------------------------
# Summarisation prompts — three-level escalation mirrors the upstream plugin.
# ---------------------------------------------------------------------------

_PROMPT_NORMAL = """\
You are a memory compressor for an AI assistant.  Summarise the following
conversation extract into a compact but lossless paragraph.  Preserve every
decision, fact, file name, error message, and instruction so the assistant can
reconstruct the full context from your summary alone.  Output the summary only
— no preamble, no commentary.

{turns}"""

_PROMPT_AGGRESSIVE = """\
Summarise the following conversation in one tight paragraph.  Keep only the
most important decisions, facts, and instructions.  Output the summary only.

{turns}"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    """Rough token count: 4 characters ≈ 1 token (good enough for budgeting)."""
    return max(1, len(text) // 4)


def _format_turns(messages: list[dict[str, str]]) -> str:
    """Format [{role, content}] as a plain-text transcript for the summary prompt."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "").upper()
        content = m.get("content", "")
        if content:
            parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


# TODO: It's a little crazy that this is in the LCM part of things, particularly because it's completely unrelated, and useful for many other things.
async def _collect_stream(stream: AsyncIterator[Any]) -> str:
    """Consume a provider stream and return all concatenated delta text."""
    parts: list[str] = []
    async for event in stream:
        if event.get("type") == "delta":
            chunk = event.get("content") or ""
            if chunk:
                parts.append(chunk)
    return "".join(parts).strip()


async def _summarize(
    provider: Any,
    turns_text: str,
    user_id: uuid.UUID,
) -> tuple[str, str]:
    """Call the provider to summarise a turn block.

    Three-level escalation:
    1. Normal prompt — full fidelity.
    2. Aggressive prompt — shorter, if normal fails or returns empty.
    3. Deterministic fallback — first 1 500 chars of the raw transcript.

    Returns:
        ``(summary_text, summary_kind)`` where ``summary_kind`` is one of
        ``"normal"``, ``"aggressive"``, or ``"fallback"``.
    """
    # Narrow exception classes to the failure modes we expect from the
    # provider/streaming layer (network, timeout, transient provider
    # errors).  Programmer errors (``TypeError``, ``AttributeError``,
    # ``ImportError``) intentionally bubble up so they surface during
    # development rather than being masked as a summarisation flake;
    # the deterministic-truncation fallback below covers the legitimate
    # transient-failure case.
    for prompt_template, kind in (
        (_PROMPT_NORMAL, "normal"),
        (_PROMPT_AGGRESSIVE, "aggressive"),
    ):
        try:
            stream = provider.stream(
                question=prompt_template.format(turns=turns_text),
                conversation_id=uuid.uuid4(),
                user_id=user_id,
                history=None,
                tools=None,
                system_prompt=None,
            )
            text = await _collect_stream(stream)
            if text:
                return text, kind
        except (OSError, RuntimeError, ValueError, TimeoutError):
            _log.warning("LCM_SUMMARIZE_%s_FAILED", kind.upper(), exc_info=True)

    # Deterministic truncation — always produces output.
    return turns_text[:_FALLBACK_TRUNCATE_CHARS], "fallback"


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------


async def compact_leaf_if_needed(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    model_id: str,
    fresh_tail_count: int,
    max_chunk_tokens: int,
) -> bool:
    """Run one leaf-compaction pass if items exist outside the fresh tail.

    Algorithm
    ---------
    1.  Fetch the full ``lcm_context_items`` list for the conversation.
    2.  If ``total_items <= fresh_tail_count`` there is nothing to compact.
    3.  The *eligible* items are the oldest ones that fall outside the fresh
        tail (``all_items[:total - fresh_tail_count]``).  Only
        ``item_kind="message"`` rows are compacted; existing summaries inside
        the eligible window are left in place (they are already compact).
    4.  Batch the oldest eligible messages up to ``max_chunk_tokens`` source
        tokens (approximate; 4 chars ≈ 1 token).
    5.  Call the provider (three-level escalation) to produce a summary.
    6.  Persist: :class:`~app.models.LCMSummary` + one
        :class:`~app.models.LCMSummarySource` per source message.
    7.  Rewrite ``lcm_context_items``: delete the compacted message rows,
        insert one ``item_kind="summary"`` row at the lowest freed ordinal
        slot.  Gaps are harmless — ``ingest_message`` uses max(ordinal)+1.

    Returns:
        ``True`` if a compaction pass ran, ``False`` if there was nothing to
        compact or the eligible window contained no un-compacted messages.
    """
    # ------------------------------------------------------------------ 1+2
    all_items = await _ensure_lcm_context_items_backfilled(session, conversation_id)
    total = len(all_items)

    if total <= fresh_tail_count:
        _log.info(
            "LCM_COMPACT_SKIP conversation_id=%s reason=too_few_items total=%d fresh_tail_limit=%d",
            conversation_id,
            total,
            fresh_tail_count,
        )
        return False

    # ------------------------------------------------------------------ 3
    eligible = all_items[: total - fresh_tail_count]
    eligible_message_ids = [item.item_id for item in eligible if item.item_kind == "message"]

    if not eligible_message_ids:
        _log.info(
            "LCM_COMPACT_SKIP conversation_id=%s reason=no_raw_messages_in_eligible total_eligible=%d",
            conversation_id,
            len(eligible),
        )
        return False  # Only summaries outside the fresh tail — nothing to do.

    # ------------------------------------------------------------------ 4
    msg_result = await session.execute(
        select(ChatMessage).where(ChatMessage.id.in_(eligible_message_ids))
    )
    messages_by_id: dict[uuid.UUID, ChatMessage] = {m.id: m for m in msg_result.scalars().all()}

    selected_items: list[LCMContextItem] = []
    selected_messages: list[dict[str, str]] = []
    running_tokens = 0

    for item in eligible:
        if item.item_kind != "message":
            continue
        msg = messages_by_id.get(item.item_id)
        if msg is None:
            continue
        msg_tokens = _approx_tokens(msg.content or "")
        if running_tokens + msg_tokens > max_chunk_tokens and selected_items:
            break
        selected_items.append(item)
        selected_messages.append({"role": msg.role, "content": msg.content or ""})
        running_tokens += msg_tokens

    if not selected_items:
        _log.info(
            "LCM_COMPACT_SKIP conversation_id=%s reason=no_selected_items eligible_message_count=%d",
            conversation_id,
            len(eligible_message_ids),
        )
        return False

    # ------------------------------------------------------------------ 5
    summary_model = settings.lcm_summary_model or model_id
    # resolve_llm currently does not accept user_id; per-user API key
    # resolution flows through workspace_root, which the chat router
    # passes in. Drop the kwarg at the call site to silence mypy.
    _ = user_id
    provider = resolve_llm(summary_model)
    turns_text = _format_turns(selected_messages)
    summary_text, summary_kind = await _summarize(provider, turns_text, user_id)

    _log.info(
        "LCM_COMPACT conversation_id=%s kind=%s sources=%d tokens=%d→%d",
        conversation_id,
        summary_kind,
        len(selected_items),
        running_tokens,
        _approx_tokens(summary_text),
    )

    # ------------------------------------------------------------------ 6
    summary_row = LCMSummary(
        conversation_id=conversation_id,
        depth=0,
        content=summary_text,
        token_count=_approx_tokens(summary_text),
        model_id=summary_model,
        summary_kind=summary_kind,
    )
    session.add(summary_row)
    await session.flush()

    for src_ordinal, item in enumerate(selected_items):
        session.add(
            LCMSummarySource(
                summary_id=summary_row.id,
                source_kind="message",
                source_id=item.item_id,
                source_ordinal=src_ordinal,
            )
        )

    # ------------------------------------------------------------------ 7
    slot_ordinal = selected_items[0].ordinal

    for item in selected_items:
        await session.delete(item)
    await session.flush()

    session.add(
        LCMContextItem(
            conversation_id=conversation_id,
            ordinal=slot_ordinal,
            item_kind="summary",
            item_id=summary_row.id,
        )
    )
    await session.flush()

    await run_condensation_cascade(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        model_id=model_id,
        max_chunk_tokens=max_chunk_tokens,
    )
    return True


# Re-export the background scheduler at package level so callers can do
# ``from app.core.lcm import schedule_lcm_compaction`` without reaching
# into ``app.core.lcm.background``. The import sits at the bottom of the
# module so ``background.py``'s own ``from app.core.lcm import
# compact_leaf_if_needed`` succeeds (that symbol is defined above).
from app.core.lcm.background import schedule_lcm_compaction  # noqa: E402

__all__ = [
    "assemble_context",
    "compact_leaf_if_needed",
    "ingest_message",
    "schedule_lcm_compaction",
]
