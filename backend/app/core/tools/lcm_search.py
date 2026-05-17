"""LCM ranked lexical search (issue #253).

``lcm_grep`` is a faithful substring tracer-bullet.  It misses any
recall where the source text and the user's question share *meaning*
but not exact tokens.  This module adds the second layer: a ranked
lexical retrieval primitive that returns scored candidates spanning
raw messages and summary nodes.

Why pure-Python scoring rather than Postgres FTS:

* The test suite uses SQLite-in-memory and there is no portable
  ``ts_vector`` story across SQLite + Postgres; we keep production +
  test parity by computing the ranking in application code over a
  coarse ``ILIKE`` candidate slice.  The ranking is explicit,
  inspectable, and easy to evolve toward a real FTS index later —
  the public ``LCMSearchResult`` shape will not change when that
  upgrade lands.
* The scorer is deterministic.  That matters for evals (issue #252):
  result ordering is reproducible without seeding randomness.

The scorer is a small term-frequency + coverage formula:

* Drop short tokens and a tight English stopword list from the query.
* Fetch every row that contains at least one query token (single
  ``ILIKE`` per token, union semantics).
* For each candidate, count how many tokens hit and how often.
* Score = ``(total_term_hits / sqrt(content_len)) * (1 + coverage_bonus) * source_weight``
* Summaries get a small source-weight bump because a hit inside a
  compacted summary covers more original conversation surface than
  one inside a raw turn.
* Recency / ordinal is a stable tie-breaker.

This is not BM25 — it is BM25's older cousin.  It is enough to beat
substring grep at paraphrased recall while staying explainable in a
single read.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Iterable, Sequence
from typing import Literal, TypedDict

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, LCMSummary

# Limits exposed via the tool schema.  Keep the defaults tight so a
# greedy agent does not blow context.  ``_MAX_LIMIT`` matches the
# upper bound in the JSON-schema parameter declaration.
_DEFAULT_LIMIT = 8
_MAX_LIMIT = 20

# Hard cap on the number of rows we score per source kind.  A coarse
# substring filter is cheap, but scoring is O(rows * tokens) — this
# guards against pathological queries on huge conversations.
_CANDIDATE_FETCH_CAP = 200

# Excerpt window in characters surrounding the highest-scoring token
# hit.  Wide enough to make the result actionable, narrow enough to
# keep the tool response token-efficient.
_EXCERPT_CHARS = 320

# Minimum token length the scorer considers.  One- and two-letter
# tokens hit too much noise (``a``, ``of``, ``is`` etc.).
_MIN_TOKEN_LEN = 3

# Multiplicative weight applied to summary scores so an equivalent
# token hit in a summary edges out one in a raw turn — summaries
# concentrate compacted history that grep would miss entirely.
_SUMMARY_SOURCE_WEIGHT = 1.2
_MESSAGE_SOURCE_WEIGHT = 1.0

# Coverage bonus added per *additional* unique query token that hits
# a candidate (the first hit gets no bonus).  Mild on purpose: we
# want multi-term matches to win over single-term spam but not so
# heavily that a partial paraphrase loses to a single-token plant.
_COVERAGE_BONUS_PER_EXTRA_TOKEN = 0.25

# Per-token TF saturation cap.  Without this, a row that repeats a
# single token N times can outrank a row that hits every term in
# the query once - that is the failure mode that motivated BM25's
# tf-saturation curve.  We use a hard cap rather than the BM25
# saturation formula because the scorer is deliberately small + easy
# to read; the saturation effect we want shows up by ~3 hits.
_TF_SATURATION = 3

# Stopwords intentionally narrow.  Removing common English filler
# words keeps the scorer signal high; keeping the list small avoids
# stripping useful domain terms that happen to be everyday English.
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "from",
        "with",
        "that",
        "this",
        "into",
        "about",
        "would",
        "should",
        "could",
        "have",
        "has",
        "had",
        "does",
        "did",
        "what",
        "which",
        "when",
        "where",
        "who",
        "why",
        "how",
        "are",
        "was",
        "were",
        "been",
        "you",
        "your",
        "our",
        "their",
        "his",
        "her",
        "its",
        "they",
        "them",
        "any",
        "all",
        "some",
        "but",
        "not",
        "yes",
        "yet",
    }
)


SearchItemKind = Literal["message", "summary"]


class LCMSearchResult(TypedDict):
    """One scored hit from :func:`lcm_search`."""

    item_kind: SearchItemKind
    item_id: str
    ordinal: int | None
    role: str | None
    summary_depth: int | None
    summary_kind: str | None
    score: float
    excerpt: str
    source_ids: list[str]


def _tokenize_query(query: str) -> list[str]:
    """Lowercase, drop stopwords, dedupe — yields the query terms used for scoring."""
    raw = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]+", query.lower())
    seen: set[str] = set()
    out: list[str] = []
    for token in raw:
        if len(token) < _MIN_TOKEN_LEN:
            continue
        if token in _STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _excerpt_around(text: str, tokens: Sequence[str]) -> str:
    """Return a substring of ``text`` around the first token hit."""
    body = text or ""
    if not body:
        return ""
    lowered = body.lower()
    earliest = len(body)
    for token in tokens:
        pos = lowered.find(token)
        if pos != -1 and pos < earliest:
            earliest = pos
    if earliest == len(body):
        return body[:_EXCERPT_CHARS] + ("…" if len(body) > _EXCERPT_CHARS else "")
    half = _EXCERPT_CHARS // 2
    start = max(0, earliest - half)
    end = min(len(body), earliest + half)
    if start == 0:
        end = min(len(body), _EXCERPT_CHARS)
    if end == len(body):
        start = max(0, len(body) - _EXCERPT_CHARS)
    snippet = body[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(body):
        snippet = snippet + "…"
    return snippet


def _score(
    content: str,
    tokens: Sequence[str],
    *,
    source_weight: float,
) -> tuple[float, int]:
    """Score one candidate.  Returns ``(score, hit_count)``.

    The TF contribution per token is saturated at ``_TF_SATURATION``
    so a row that repeats a single query token cannot drown a row
    that hits multiple distinct tokens once each (which is the
    motivating failure for issue #253 - paraphrased multi-term
    recall must beat a single-token plant).
    """
    body = (content or "").lower()
    if not body:
        return 0.0, 0
    contribution_total = 0.0
    distinct_hits = 0
    total_hits = 0
    for token in tokens:
        if not token:
            continue
        # ``str.count`` returns non-overlapping count, which is what
        # we want for term-frequency-style scoring.
        hits = body.count(token)
        if hits == 0:
            continue
        distinct_hits += 1
        total_hits += hits
        contribution_total += min(hits, _TF_SATURATION)
    if contribution_total == 0.0:
        return 0.0, 0
    coverage_bonus = max(0, distinct_hits - 1) * _COVERAGE_BONUS_PER_EXTRA_TOKEN
    length_norm = math.sqrt(max(len(body), 1))
    raw = contribution_total / length_norm
    return raw * (1.0 + coverage_bonus) * source_weight, total_hits


def _normalise_limit(limit: int | None) -> int:
    """Clamp ``limit`` to the safe range; falls back to the default when missing."""
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(_MAX_LIMIT, int(limit)))


async def _fetch_message_candidates(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    tokens: Sequence[str],
) -> list[ChatMessage]:
    """Coarse ILIKE-OR filter: rows that contain *at least one* query token."""
    if not tokens:
        return []
    clauses = [ChatMessage.content.ilike(f"%{token}%") for token in tokens]
    result = await session.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role.in_(["user", "assistant"]),
            or_(*clauses),
        )
        .order_by(ChatMessage.ordinal.desc())
        .limit(_CANDIDATE_FETCH_CAP)
    )
    return list(result.scalars().all())


async def _fetch_summary_candidates(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    tokens: Sequence[str],
) -> list[LCMSummary]:
    """Coarse ILIKE-OR filter for summary rows."""
    if not tokens:
        return []
    clauses = [LCMSummary.content.ilike(f"%{token}%") for token in tokens]
    result = await session.execute(
        select(LCMSummary)
        .where(
            LCMSummary.conversation_id == conversation_id,
            or_(*clauses),
        )
        .order_by(LCMSummary.created_at.desc())
        .limit(_CANDIDATE_FETCH_CAP)
    )
    return list(result.scalars().all())


def _build_message_result(
    msg: ChatMessage,
    *,
    tokens: Sequence[str],
    score: float,
) -> LCMSearchResult:
    """Wrap a scored message row as the public result shape."""
    return LCMSearchResult(
        item_kind="message",
        item_id=str(msg.id),
        ordinal=msg.ordinal,
        role=msg.role,
        summary_depth=None,
        summary_kind=None,
        score=round(score, 6),
        excerpt=_excerpt_around(msg.content or "", tokens),
        source_ids=[str(msg.id)],
    )


def _build_summary_result(
    summary: LCMSummary,
    *,
    tokens: Sequence[str],
    score: float,
) -> LCMSearchResult:
    """Wrap a scored summary row as the public result shape."""
    return LCMSearchResult(
        item_kind="summary",
        item_id=str(summary.id),
        ordinal=None,
        role=None,
        summary_depth=summary.depth,
        summary_kind=summary.summary_kind,
        score=round(score, 6),
        excerpt=_excerpt_around(summary.content or "", tokens),
        source_ids=[str(summary.id)],
    )


def _ranked_messages(
    rows: Iterable[ChatMessage],
    *,
    tokens: Sequence[str],
) -> list[LCMSearchResult]:
    """Score every message candidate and return the ones with non-zero hits."""
    results: list[LCMSearchResult] = []
    for row in rows:
        score, hits = _score(row.content or "", tokens, source_weight=_MESSAGE_SOURCE_WEIGHT)
        if hits == 0:
            continue
        results.append(_build_message_result(row, tokens=tokens, score=score))
    return results


def _ranked_summaries(
    rows: Iterable[LCMSummary],
    *,
    tokens: Sequence[str],
) -> list[LCMSearchResult]:
    """Score every summary candidate and return the ones with non-zero hits."""
    results: list[LCMSearchResult] = []
    for row in rows:
        score, hits = _score(row.content or "", tokens, source_weight=_SUMMARY_SOURCE_WEIGHT)
        if hits == 0:
            continue
        results.append(_build_summary_result(row, tokens=tokens, score=score))
    return results


async def lcm_search(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    query: str,
    limit: int | None = None,
    include_messages: bool = True,
    include_summaries: bool = True,
) -> list[LCMSearchResult]:
    """Run ranked lexical search over a conversation's messages + summaries.

    Args:
        session: Open async database session.
        conversation_id: Conversation whose history is in scope.
        query: User-supplied query string.
        limit: Cap on the number of results returned.  Clamped to
            ``_MAX_LIMIT``; falls back to ``_DEFAULT_LIMIT`` when
            unset or non-positive.
        include_messages: Include scored raw messages in the result.
        include_summaries: Include scored summary nodes in the result.

    Returns:
        A list of :class:`LCMSearchResult` ordered by score descending.
        Empty when the query is empty, when no tokens survive
        normalisation, or when nothing scored above zero.
    """
    tokens = _tokenize_query(query)
    if not tokens:
        return []

    capped = _normalise_limit(limit)

    messages: list[ChatMessage] = []
    if include_messages:
        messages = await _fetch_message_candidates(
            session, conversation_id=conversation_id, tokens=tokens
        )
    summaries: list[LCMSummary] = []
    if include_summaries:
        summaries = await _fetch_summary_candidates(
            session, conversation_id=conversation_id, tokens=tokens
        )

    scored: list[LCMSearchResult] = _ranked_messages(messages, tokens=tokens)
    scored.extend(_ranked_summaries(summaries, tokens=tokens))

    # Recency / ordinal tie-breaker: higher score first, then most
    # recent ordinal/depth first (depth ascending — leaves first).
    scored.sort(
        key=lambda r: (
            -r["score"],
            -(r["ordinal"] or 0),
            r["summary_depth"] or 0,
        )
    )
    return scored[:capped]


def format_results(query: str, results: Sequence[LCMSearchResult]) -> str:
    """Render search results as the compact text block the agent receives."""
    if not results:
        return f"lcm_search: no ranked matches for {query!r}"
    lines: list[str] = [
        f"lcm_search: {len(results)} result(s) for {query!r}",
    ]
    for index, result in enumerate(results, start=1):
        meta = _format_result_metadata(result)
        lines.append(f"\n[{index}] score={result['score']:.3f} {meta}\n{result['excerpt']}")
    return "\n".join(lines)


def _format_result_metadata(result: LCMSearchResult) -> str:
    """One-liner metadata header for a scored result."""
    if result["item_kind"] == "message":
        return (
            f"kind=message role={result['role']} ordinal={result['ordinal']} id={result['item_id']}"
        )
    return (
        f"kind=summary depth={result['summary_depth']} "
        f"summary_kind={result['summary_kind']} id={result['item_id']}"
    )
