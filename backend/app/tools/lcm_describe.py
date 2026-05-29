"""LCM describe — cheap inspection of a single LCMSummary node.

This is the backing implementation for the ``lcm_describe`` agent tool
introduced in PR #5 of the LCM stack.

Use case
--------
After ``lcm_grep`` returns a match inside a summary node, the agent may want
to read the *full* summary text (not just the excerpt).  ``lcm_describe``
fetches the complete node and its metadata in one cheap DB round-trip.

It also exposes ``lcm_list_summaries`` so the agent can enumerate all summary
nodes for the current conversation and pick the right one to inspect.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LCMSummary, LCMSummarySource

# Number of characters from a summary's content shown as the per-node
# excerpt in ``lcm_list_summaries``.  Wide enough to pick up the first
# sentence; narrow enough to keep the list compact in agent context.
_LIST_EXCERPT_CHARS = 120


def _format_summary(
    summary: LCMSummary,
    sources: list[LCMSummarySource],
    *,
    include_full_content: bool = True,
) -> str:
    """Format a summary node and its source edges as a readable string."""
    lines: list[str] = [
        f"Summary ID:   {summary.id}",
        f"Depth:        {summary.depth}",
        f"Kind:         {summary.summary_kind}",
        f"Model:        {summary.model_id or '(unknown)'}",
        f"Tokens:       ~{summary.token_count}",
        f"Created:      {summary.created_at.isoformat()}",
        f"Sources:      {len(sources)} item(s)",
    ]
    if sources:
        lines.extend(f"  [{s.source_ordinal}] {s.source_kind} id={s.source_id}" for s in sources)
    if include_full_content:
        lines.append("")
        lines.append("Content:")
        lines.append(summary.content)
    return "\n".join(lines)


async def lcm_describe(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    summary_id: uuid.UUID,
) -> str:
    """Return the full content and metadata of a single LCMSummary node.

    The lookup is scoped to *conversation_id* so the agent cannot inspect
    summaries from other conversations even if it somehow obtains a foreign ID.

    Args:
        session: Open async database session.
        conversation_id: Conversation the summary must belong to.
        summary_id: UUID of the target :class:`~app.models.LCMSummary`.

    Returns:
        A formatted multi-line string with the summary's metadata and full
        content, or an error string if not found.
    """
    result = await session.execute(
        select(LCMSummary).where(
            LCMSummary.id == summary_id,
            LCMSummary.conversation_id == conversation_id,
        )
    )
    summary = result.scalar_one_or_none()

    if summary is None:
        return (
            f"lcm_describe: summary {summary_id} not found "
            f"(may belong to a different conversation, or may not exist)."
        )

    sources_result = await session.execute(
        select(LCMSummarySource)
        .where(LCMSummarySource.summary_id == summary.id)
        .order_by(LCMSummarySource.source_ordinal)
    )
    sources = list(sources_result.scalars().all())

    return _format_summary(summary, sources, include_full_content=True)


async def lcm_list_summaries(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
) -> str:
    """List all LCMSummary nodes for a conversation, most-recent-first.

    Returns a compact table showing each node's ID, depth, kind, and a
    brief excerpt so the agent can decide which one to inspect further.
    """
    result = await session.execute(
        select(LCMSummary)
        .where(LCMSummary.conversation_id == conversation_id)
        .order_by(LCMSummary.created_at.desc())
    )
    summaries = list(result.scalars().all())

    if not summaries:
        return "lcm_list_summaries: no summaries exist for this conversation yet."

    header = f"lcm_list_summaries: {len(summaries)} node(s)\n"
    rows: list[str] = []
    for s in summaries:
        excerpt = s.content[:_LIST_EXCERPT_CHARS].replace("\n", " ")
        if len(s.content) > _LIST_EXCERPT_CHARS:
            excerpt += "…"
        rows.append(
            f"  id={s.id}  depth={s.depth}  kind={s.summary_kind}  "
            f"tokens=~{s.token_count}\n    {excerpt}"
        )
    return header + "\n".join(rows)
