"""LCM condensation — fold same-depth summaries into deeper parent nodes.

Split out of ``app.lcm`` to keep that module under the 500-line
file budget while keeping the call surface tiny:
:func:`run_condensation_cascade` is the single seam
``compact_leaf_if_needed`` calls after a successful leaf compaction.

The condensation pass is what prevents unbounded growth of leaf
summaries: once two depth-0 summaries exist, the next compaction
folds them into a depth-1 parent, and so on.  Controlled by
``settings.lcm_incremental_max_depth`` (0 = leaf-only, 1 = one pass,
-1 = unlimited cascade capped at :data:`_CONDENSATION_HARD_CAP`).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import settings as settings  # noqa: PLC0414
from app.lcm.summarization import (
    _approx_tokens,
    _format_turns,
    _resolve_summary_provider,
    _summarize,
)
from app.models import LCMContextItem, LCMSummary, LCMSummarySource

_log = logging.getLogger(__name__)

# Minimum number of same-depth summaries required before condensation
# kicks in.  Two is the natural floor: condensation folds N summaries
# into one parent, so a single summary cannot meaningfully condense.
_MIN_CONDENSE_SOURCES = 2

# Practical safety cap on the unlimited-cascade option
# (``lcm_incremental_max_depth == -1``).  No reasonable conversation
# produces 999 condensation depths; the cap exists purely to keep a
# runaway feedback loop from blocking the event loop.
_CONDENSATION_HARD_CAP = 999


async def run_condensation_cascade(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    model_id: str,
    max_chunk_tokens: int,
) -> None:
    """Fold accumulated leaf summaries into deeper parent nodes.

    Controlled by ``settings.lcm_incremental_max_depth``:

    * ``0``  — leaf-only (no condensation)
    * ``1``  — one pass (leaf → depth-1) [default]
    * ``-1`` — unlimited cascade, capped at :data:`_CONDENSATION_HARD_CAP`
    """
    if settings.lcm_incremental_max_depth == 0:
        return
    passes = (
        settings.lcm_incremental_max_depth
        if settings.lcm_incremental_max_depth > 0
        else _CONDENSATION_HARD_CAP
    )
    for depth in range(passes):
        ran = await _condense_at_depth(
            session,
            conversation_id=conversation_id,
            user_id=user_id,
            model_id=model_id,
            depth=depth,
            max_chunk_tokens=max_chunk_tokens,
        )
        if not ran:
            return


async def _condense_at_depth(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    model_id: str,
    depth: int,
    max_chunk_tokens: int,
) -> bool:
    """Run one condensation pass: merge depth-*d* summaries into a depth-*(d+1)* parent.

    Finds all ``LCMContextItem`` rows whose backing ``LCMSummary`` has the
    given *depth*.  If at least two such items exist, takes the oldest batch
    (up to *max_chunk_tokens* source tokens), calls the provider to produce a
    parent summary, writes ``LCMSummary`` (depth+1) + ``LCMSummarySource``
    edges, and replaces the compacted context items with a single
    ``item_kind="summary"`` row pointing at the new parent.

    Returns:
        ``True`` if a condensation pass ran, ``False`` if fewer than 2
        eligible items exist (nothing to condense at this depth).
    """
    all_items_result = await session.execute(
        select(LCMContextItem)
        .where(LCMContextItem.conversation_id == conversation_id)
        .order_by(LCMContextItem.ordinal.asc())
    )
    all_items = list(all_items_result.scalars().all())

    summary_item_ids = [i.item_id for i in all_items if i.item_kind == "summary"]
    if not summary_item_ids:
        return False

    # Filter by ``depth`` at the DB layer so a context list that holds
    # summaries at multiple depths (one depth-0, one depth-1, ...) only
    # round-trips the rows that this pass could actually fold.  The
    # previous shape counted summaries-at-any-depth in a Python-side
    # guard and then issued the IN-query anyway when the count was ≥ 2,
    # which wasted a query whenever the depth-specific subset was < 2.
    s_result = await session.execute(
        select(LCMSummary).where(
            LCMSummary.id.in_(summary_item_ids),
            LCMSummary.depth == depth,
        )
    )
    summaries_by_id: dict[uuid.UUID, LCMSummary] = {s.id: s for s in s_result.scalars().all()}

    if len(summaries_by_id) < _MIN_CONDENSE_SOURCES:
        return False

    eligible: list[tuple[LCMContextItem, LCMSummary]] = [
        (item, summaries_by_id[item.item_id])
        for item in all_items
        if item.item_kind == "summary" and item.item_id in summaries_by_id
    ]

    selected_items: list[LCMContextItem] = []
    selected_messages: list[dict[str, str]] = []
    running_tokens = 0

    for item, summ in eligible:
        toks = _approx_tokens(summ.content)
        if running_tokens + toks > max_chunk_tokens and selected_items:
            break
        selected_items.append(item)
        selected_messages.append(
            {
                "role": "user",
                "content": f"[Summary depth={summ.depth}]\n{summ.content}",
            }
        )
        running_tokens += toks

    if len(selected_items) < _MIN_CONDENSE_SOURCES:
        return False

    turns_text = _format_turns(selected_messages)
    summary_text, summary_kind = await _summarize(
        # resolve_llm does not accept user_id; kept as unused param for
        # call-site symmetry with workspace key resolution upstream.
        _resolve_summary_provider(settings.lcm_summary_model or model_id),
        turns_text,
        user_id,
    )

    _log.info(
        "LCM_CONDENSE depth=%d→%d conversation_id=%s sources=%d",
        depth,
        depth + 1,
        conversation_id,
        len(selected_items),
    )

    parent = LCMSummary(
        conversation_id=conversation_id,
        depth=depth + 1,
        content=summary_text,
        token_count=_approx_tokens(summary_text),
        model_id=settings.lcm_summary_model or model_id,
        summary_kind=summary_kind,
    )
    session.add(parent)
    await session.flush()

    for src_ordinal, item in enumerate(selected_items):
        session.add(
            LCMSummarySource(
                summary_id=parent.id,
                source_kind="summary",
                source_id=item.item_id,
                source_ordinal=src_ordinal,
            )
        )

    slot_ordinal = selected_items[0].ordinal
    for item in selected_items:
        await session.delete(item)
    await session.flush()

    session.add(
        LCMContextItem(
            conversation_id=conversation_id,
            ordinal=slot_ordinal,
            item_kind="summary",
            item_id=parent.id,
        )
    )
    await session.flush()
    return True
