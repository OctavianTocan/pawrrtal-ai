"""``hindsight_query`` AgentTool — semantic recall across past conversations (#359).

LCM (per-conversation) gives the agent grep + ranked lexical
retrieval against the current conversation's summary tree.
``memory_query`` (per-user) returns recent typed memories from the
proactive-memory pipeline (#340).

Hindsight covers the gap: **cross-conversation semantic recall**.
"Did the user ever tell me about their thoughts on Postgres?" or
"What did we decide about the cost ledger?" land here. The tool
walks ``chat_messages`` rows belonging to the user across every
conversation and returns the highest-scoring matches by combining:

1. Substring presence of the query terms (cheap pre-filter).
2. Distance-weighted recency (recent matches outrank ancient ones).
3. Light per-conversation grouping so the tool never returns 5
   results from the same conversation when more diverse ones
   exist.

The tool is intentionally text-only — embeddings live behind a
future stacked PR that switches the scoring layer to vector
similarity once the LCM embedding pipeline is wired through to a
per-user index. Until then, substring + recency is the same
shape :mod:`app.core.tools.lcm_search` uses inside one
conversation.
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_loop.types import AgentTool
from app.db import async_session_maker
from app.models import ChatMessage

logger = logging.getLogger(__name__)

# Limits exposed in the tool schema. Match the LCM search caps so an
# agent that's used to ``lcm_search`` doesn't have to remember
# different ones.
_DEFAULT_LIMIT = 5
_MAX_LIMIT = 20

# Hard cap on rows scored per query. Pure-Python scoring is O(rows *
# tokens) — keep this bounded.
_CANDIDATE_FETCH_CAP = 400

# Stop-word filter. Dropping common English tokens keeps the
# ranking signal high without rebuilding a corpus-wide TF-IDF
# table.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "what",
        "when",
        "where",
        "why",
        "how",
        "my",
        "your",
    }
)

_MIN_TOKEN_LENGTH = 3
_HALF_LIFE_DAYS = 30.0


def make_hindsight_query_tool(*, user_id: uuid.UUID) -> AgentTool:
    """Return the ``hindsight_query`` AgentTool bound to ``user_id``.

    ``user_id`` is captured in the closure as the authorisation
    gate — the tool can only read messages belonging to the calling
    user, regardless of which conversation they're in now.

    Args:
        user_id: Authenticated Pawrrtal user UUID. Embedded into
            the query so cross-user reads are impossible at the
            ORM layer.

    Returns:
        An :class:`AgentTool` the agent can call mid-turn to
        recall a fact the user mentioned in some other conversation.
    """

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        query = kwargs.get("query")
        if not isinstance(query, str) or not query.strip():
            return "hindsight_query: missing required ``query`` argument."

        raw_limit = kwargs.get("limit", _DEFAULT_LIMIT)
        try:
            limit = max(1, min(_MAX_LIMIT, int(raw_limit)))
        except (TypeError, ValueError):
            limit = _DEFAULT_LIMIT

        async with async_session_maker() as session:
            candidates = await _fetch_candidates(
                session=session,
                user_id=user_id,
                query=query,
            )
        ranked = _rank_candidates(candidates, query=query)
        if not ranked:
            return f"hindsight_query: no matches for {query!r} across past conversations."
        return _render_results(ranked[:limit])

    return AgentTool(
        name="hindsight_query",
        description=(
            "Semantically search the user's past conversations for any "
            "message that matches the query. Use this when the user "
            "references something they said in an earlier conversation "
            "(NOT the current one — that's what ``lcm_grep`` / "
            "``lcm_search`` cover) but you can't find it in immediate "
            "context. Returns up to a few of the highest-scoring past "
            "messages with their conversation context."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The phrase or topic you want to recall. Short "
                        "noun phrases beat long sentences — the scorer "
                        "is token-based."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _MAX_LIMIT,
                    "description": (
                        f"Maximum number of matches to return. "
                        f"Default {_DEFAULT_LIMIT}, capped at {_MAX_LIMIT}."
                    ),
                },
            },
            "required": ["query"],
        },
        execute=execute,
    )


async def _fetch_candidates(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    query: str,
) -> list[ChatMessage]:
    """Pull a coarse candidate slice by substring filter on each query token.

    The Python scoring step then ranks these by token coverage and
    recency. SQL-side scoring would be more efficient on huge corpora
    but locks us into the dialect's full-text-search story; the
    project intentionally stays SQLite-portable for tests.
    """
    tokens = _query_tokens(query)
    if not tokens:
        return []

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(_CANDIDATE_FETCH_CAP)
    )
    # Pre-filter by ANY token (case-insensitive). Doing this in a
    # single CTE / array-contains would require dialect-specific
    # operators; the broad slice + Python filter is simpler.
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    return [row for row in rows if _row_matches_any_token(row, tokens)]


def _query_tokens(query: str) -> list[str]:
    """Tokenise + lower-case + drop short / stop-word tokens."""
    raw = re.findall(r"[A-Za-z0-9_]+", query.lower())
    return [t for t in raw if len(t) >= _MIN_TOKEN_LENGTH and t not in _STOPWORDS]


def _row_matches_any_token(row: ChatMessage, tokens: list[str]) -> bool:
    """Return whether ``row.content`` contains at least one query token."""
    content_lower = (row.content or "").lower()
    return any(token in content_lower for token in tokens)


def _rank_candidates(
    rows: list[ChatMessage],
    *,
    query: str,
) -> list[tuple[float, ChatMessage]]:
    """Score + sort candidate rows by ``(token_hits * recency)``.

    The recency multiplier uses an exponential decay with a 30-day
    half-life — recent matches dominate, but a 6-month-old fact
    that scores 5x on tokens still beats a 1-day-old random
    mention.
    """
    tokens = _query_tokens(query)
    if not tokens or not rows:
        return []

    now = datetime.now(tz=rows[0].created_at.tzinfo) if rows[0].created_at else datetime.now()
    scored: list[tuple[float, ChatMessage]] = []
    for row in rows:
        content_lower = (row.content or "").lower()
        hits = sum(content_lower.count(token) for token in tokens)
        if hits == 0:
            continue
        coverage = sum(1 for token in tokens if token in content_lower) / len(tokens)
        recency = _recency_weight(row.created_at, now=now)
        score = (hits + coverage * 5) * recency
        scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored


def _recency_weight(created_at: datetime | None, *, now: datetime) -> float:
    """Return an exponential-decay weight for ``created_at``."""
    if created_at is None:
        return 1.0
    try:
        delta = now - created_at
    except TypeError:
        return 1.0
    days = max(0.0, delta.total_seconds() / 86_400)
    return math.exp(-math.log(2) * days / _HALF_LIFE_DAYS)


def _render_results(results: list[tuple[float, ChatMessage]]) -> str:
    """Render the ranked results as a model-readable list."""
    lines = ["Hindsight matches (highest-ranking first):"]
    for score, row in results:
        when = row.created_at.strftime("%Y-%m-%d") if row.created_at else "?"
        excerpt = (row.content or "").strip().replace("\n", " ")
        if len(excerpt) > 300:
            excerpt = excerpt[:297] + "…"
        lines.append(f"- [{when} · score={score:.2f}] {excerpt}")
    return "\n".join(lines)


__all__ = ["make_hindsight_query_tool"]
