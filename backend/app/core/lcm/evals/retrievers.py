"""Retrieval implementations for each :class:`LCMEvalMode`.

Every retrieval mode the harness compares lives here as an
``async def retrieve_*`` coroutine returning ``(blob, tools_called)``.
The runner module wraps each one in a uniform dispatch-table
signature; the retrievers themselves stay close to the production
APIs they exercise (``assemble_context``, ``lcm_grep``, ``lcm_search``,
``lcm_hybrid_search``, ``pack_context``) so reviewers can diff
harness vs production behaviour at a glance.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm import assemble_context
from app.core.lcm.embeddings import (
    DeterministicHashEmbedder,
    Embedder,
    lcm_hybrid_search,
)
from app.core.lcm.pack import PackCandidate, pack_context
from app.core.tools.lcm_grep import lcm_grep
from app.core.tools.lcm_search import LCM_STOPWORDS, lcm_search
from app.core.tools.lcm_search import format_results as format_search_results
from app.models import ChatMessage

# Same 4-chars-per-token approximation used everywhere else in LCM.
_CHARS_PER_TOKEN = 4

# Hard cap on retrieved-context characters surfaced to the answerer.
# Keeps CI runtime stable when a scenario seeds a huge transcript.
_MAX_CONTEXT_CHARS = 64_000

# Default lcm_grep result cap when the mode-specific runner does not
# pass one through.  Matches the production tool's default so the
# harness measures realistic behaviour.
_GREP_RESULT_CAP = 10

# Maximum number of content-bearing terms extracted from a question
# before they are fanned out across :func:`lcm_grep` calls.
_MAX_SEARCH_TERMS = 5


def _flatten_assembled(context: list[dict[str, object]]) -> str:
    """Concatenate an assembled-context list into a single text blob."""
    parts: list[str] = []
    for turn in context:
        role = str(turn.get("role") or "")
        content = str(turn.get("content") or "")
        if content:
            parts.append(f"{role.upper()}: {content}")
    blob = "\n\n".join(parts)
    return blob[:_MAX_CONTEXT_CHARS]


def _extract_search_terms(question: str) -> list[str]:
    """Pull a handful of content-bearing words out of a question.

    Uses the shared :data:`app.core.tools.lcm_search.LCM_STOPWORDS`
    set so the eval harness tokenises identically to the retrieval
    scorer it benchmarks.
    """
    raw_tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", question.lower())
    seen: set[str] = set()
    terms: list[str] = []
    for token in raw_tokens:
        if token in LCM_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms[:_MAX_SEARCH_TERMS]


async def retrieve_baseline(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Baseline: the old ``LIMIT 20``-style raw-tail slice — no LCM machinery."""
    result = await session.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role.in_(["user", "assistant"]),
        )
        .order_by(ChatMessage.ordinal.desc())
        .limit(fresh_tail_count)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    blob = "\n\n".join(f"{m.role.upper()}: {m.content or ''}" for m in rows)
    return blob[:_MAX_CONTEXT_CHARS], []


async def retrieve_lcm_assembled(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """LCM mode: protected fresh tail + every summary, via :func:`assemble_context`."""
    context = await assemble_context(
        session,
        conversation_id=conversation_id,
        fresh_tail_count=fresh_tail_count,
    )
    return _flatten_assembled(context), []


async def retrieve_lcm_grep(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    question: str,
) -> tuple[str, list[str]]:
    """Grep-assisted recall: synthesise short queries, union the matches.

    Picks the longest few content words from ``question`` and runs them
    through :func:`lcm_grep`.  The deterministic answerer then quotes
    matching spans.  We do not stitch grep output into a chat call
    because the harness's answerer is intentionally retrieval-only.
    """
    queries = _extract_search_terms(question)
    blob_parts: list[str] = []
    for term in queries:
        snippet = await lcm_grep(
            session,
            conversation_id=conversation_id,
            query=term,
            limit=_GREP_RESULT_CAP,
        )
        blob_parts.append(snippet)
    blob = "\n\n".join(blob_parts)
    return blob[:_MAX_CONTEXT_CHARS], ["lcm_grep"]


async def retrieve_lcm_search(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    question: str,
) -> tuple[str, list[str]]:
    """Ranked lexical retrieval via :func:`lcm_search`."""
    results = await lcm_search(
        session,
        conversation_id=conversation_id,
        query=question,
    )
    blob = format_search_results(question, results)
    return blob[:_MAX_CONTEXT_CHARS], ["lcm_search"]


async def retrieve_hybrid(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    question: str,
    mode: str,
    embedder: Embedder | None = None,
) -> tuple[str, list[str]]:
    """Hybrid (or one-leg) retrieval via :func:`lcm_hybrid_search`."""
    used_embedder = embedder or DeterministicHashEmbedder()
    rows = await lcm_hybrid_search(
        session,
        conversation_id=conversation_id,
        query=question,
        mode=mode,  # type: ignore[arg-type]
        embedder=used_embedder,
    )
    parts = [
        f"[{row['item_kind'].upper()} score={row['final_score']:.3f}] {row['excerpt']}"
        for row in rows
    ]
    blob = "\n\n".join(parts)
    tools = (
        ["lcm_search", "semantic_search"]
        if mode == "hybrid"
        else (["lcm_search"] if mode == "lexical" else ["semantic_search"])
    )
    return blob[:_MAX_CONTEXT_CHARS], tools


async def retrieve_lcm_search_packed(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    question: str,
) -> tuple[str, list[str]]:
    """Ranked search routed through the issue-#255 context packer."""
    raw_results = await lcm_search(
        session,
        conversation_id=conversation_id,
        query=question,
    )
    candidates: list[PackCandidate] = [
        PackCandidate(
            item_kind=row["item_kind"],
            item_id=row["item_id"],
            ordinal=row.get("ordinal"),
            role=row.get("role"),
            summary_depth=row.get("summary_depth"),
            summary_kind=row.get("summary_kind"),
            source_ids=list(row.get("source_ids") or []),
            lexical_score=row.get("score"),
            final_score=row.get("score"),
            excerpt=row.get("excerpt", ""),
            content=row.get("excerpt", ""),
            token_count=max(1, len(row.get("excerpt", "")) // _CHARS_PER_TOKEN),
        )
        for row in raw_results
    ]
    packed = pack_context(candidates, query=question)
    rendered_parts = [
        f"[{item['item_kind'].upper()} reason={item['packed_reason']}]\n{item['content']}"
        for item in packed["kept"]
    ]
    blob = "\n\n".join(rendered_parts)
    return blob[:_MAX_CONTEXT_CHARS], ["lcm_search", "pack_context"]
