"""LCM grep — search conversation history across messages and summaries.

This is the backing implementation for the ``lcm_grep`` agent tool introduced
in PR #4 of the LCM stack.

Design
------
The upstream lossless-claw plugin uses SQLite FTS5 for full-text search.
We run Postgres in production, where a dedicated ``tsvector`` index is the
right long-term solution (tracked in ``.beans/lcm-followups.md``).  For this
tracer-bullet PR we use ``ILIKE '%query%'`` which works on both SQLite (tests)
and Postgres (production) without a schema migration.  The FTS upgrade can
land in a follow-up once we have real production workloads to benchmark.

Returned result format
----------------------
Each match is a compact block::

    [MESSAGE role=user ordinal=12]
    ...matching content excerpt...

    [SUMMARY depth=0]
    ...matching summary excerpt...

Matches are capped at ``max_excerpt_chars`` per entry to keep the response
token-efficient.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, LCMSummary

_MAX_RESULTS_DEFAULT = 10
_MAX_EXCERPT_CHARS = 500


def _excerpt(text: str, *, query: str, max_chars: int = _MAX_EXCERPT_CHARS) -> str:
    """Return a snippet around the first occurrence of *query* in *text*.

    The snippet is at most *max_chars* characters.  If the match is near
    the start or end, the window shifts to fit; the edge is marked with ``…``
    when content is elided.
    """
    text = text or ""
    query_lower = query.lower()
    pos = text.lower().find(query_lower)
    if pos == -1:
        # Shouldn't happen (we searched for the query), but handle gracefully.
        return text[:max_chars] + ("…" if len(text) > max_chars else "")

    half = max_chars // 2
    start = max(0, pos - half)
    end = min(len(text), pos + len(query) + half)

    # Expand the window to *max_chars* if we hit an edge.
    if start == 0:
        end = min(len(text), max_chars)
    if end == len(text):
        start = max(0, len(text) - max_chars)

    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _format_results(
    message_hits: list[ChatMessage],
    summary_hits: list[LCMSummary],
    query: str,
) -> str:
    """Format matched rows as a compact markdown-ish string for the agent."""
    if not message_hits and not summary_hits:
        return f"No matches found for query: {query!r}"

    parts: list[str] = []

    for msg in message_hits:
        exc = _excerpt(msg.content or "", query=query)
        parts.append(f"[MESSAGE role={msg.role} ordinal={msg.ordinal}]\n{exc}")

    for summ in summary_hits:
        exc = _excerpt(summ.content or "", query=query)
        parts.append(f"[SUMMARY depth={summ.depth} kind={summ.summary_kind}]\n{exc}")

    header = (
        f"lcm_grep: {len(message_hits)} message match(es), "
        f"{len(summary_hits)} summary match(es) for {query!r}\n"
    )
    return header + "\n\n".join(parts)


async def lcm_grep(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    query: str,
    limit: int = _MAX_RESULTS_DEFAULT,
) -> str:
    """Search a conversation's messages and summaries for *query*.

    Performs case-insensitive substring matching across:

    * ``chat_messages.content`` — raw user/assistant turns
    * ``lcm_summaries.content`` — compacted history nodes

    Both searches are scoped to *conversation_id*.  Results are ordered
    most-recent-first and capped at *limit* per source.  The combined output
    is formatted as a compact annotated text block suitable for direct
    inclusion in an agent's tool result.

    Args:
        session: Open async database session.
        conversation_id: Conversation to search.
        query: The search string.  Matched case-insensitively as a substring.
        limit: Maximum number of results per source (messages + summaries each).

    Returns:
        A formatted string with matches and excerpts, or a "no matches"
        message if nothing matched.
    """
    if not query.strip():
        return "lcm_grep: empty query — nothing to search."

    # SQLAlchemy's ``.ilike()`` emits ``ILIKE`` on Postgres and
    # ``LIKE LOWER(...)`` on SQLite — both work for our needs.
    msg_result = await session.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role.in_(["user", "assistant"]),
            ChatMessage.content.ilike(f"%{query}%"),
        )
        .order_by(ChatMessage.ordinal.desc())
        .limit(limit)
    )
    message_hits = list(msg_result.scalars().all())

    sum_result = await session.execute(
        select(LCMSummary)
        .where(
            LCMSummary.conversation_id == conversation_id,
            LCMSummary.content.ilike(f"%{query}%"),
        )
        .order_by(LCMSummary.created_at.desc())
        .limit(limit)
    )
    summary_hits = list(sum_result.scalars().all())

    return _format_results(message_hits, summary_hits, query)
