"""Cosine-similarity search across stored embedding rows.

Returns ranked :class:`SemanticHit` objects scoped to one
conversation.  The hybrid blender layers this on top of lexical
search via Reciprocal Rank Fusion (see :mod:`.hybrid`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm.embeddings.embedder import (
    DeterministicHashEmbedder,
    Embedder,
    ItemKind,
    cosine_similarity,
)
from app.core.tools.lcm_search import _excerpt_around, _tokenize_query
from app.models import ChatMessage, LCMEmbedding, LCMSummary

# Default cap on the number of semantic candidates pulled from the
# DB before scoring.  Same shape as ``lcm_search``'s candidate fetch
# cap; protects against pathological conversations.
_SEMANTIC_CANDIDATE_CAP = 200


@dataclass(frozen=True)
class SemanticHit:
    """Internal hit shape used while assembling search results."""

    item_kind: ItemKind
    item_id: str
    score: float
    excerpt: str
    metadata: dict[str, object]


async def semantic_search(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    query: str,
    limit: int = 8,
    embedder: Embedder | None = None,
) -> list[SemanticHit]:
    """Run cosine-similarity search over stored embeddings.

    Returns ranked hits scoped to one conversation.  Empty queries
    short-circuit to ``[]`` so callers do not need to pre-filter.
    """
    query_body = (query or "").strip()
    if not query_body:
        return []
    used_embedder = embedder or DeterministicHashEmbedder()
    query_vector = used_embedder.embed(query_body)

    rows = await _fetch_embeddings(
        session,
        conversation_id=conversation_id,
        embedding_model=used_embedder.model_id,
    )
    if not rows:
        return []

    enriched = await _resolve_excerpts(session, rows, query_body)
    scored: list[SemanticHit] = []
    for row, excerpt, metadata in enriched:
        sim = cosine_similarity(query_vector, row.embedding)
        if sim <= 0.0:
            continue
        scored.append(
            SemanticHit(
                item_kind=row.item_kind,  # type: ignore[arg-type]
                item_id=str(row.item_id),
                score=round(sim, 6),
                excerpt=excerpt,
                metadata=metadata,
            )
        )
    scored.sort(key=lambda hit: -hit.score)
    return scored[:limit]


async def _fetch_embeddings(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    embedding_model: str,
) -> list[LCMEmbedding]:
    """Pull all stored embeddings for a conversation + model."""
    result = await session.execute(
        select(LCMEmbedding)
        .where(
            LCMEmbedding.conversation_id == conversation_id,
            LCMEmbedding.embedding_model == embedding_model,
        )
        .limit(_SEMANTIC_CANDIDATE_CAP)
    )
    return list(result.scalars().all())


async def _resolve_excerpts(
    session: AsyncSession,
    rows: Iterable[LCMEmbedding],
    query: str,
) -> list[tuple[LCMEmbedding, str, dict[str, object]]]:
    """Join each embedding row to its source content for excerpting."""
    rows_list = list(rows)
    message_ids = [row.item_id for row in rows_list if row.item_kind == "message"]
    summary_ids = [row.item_id for row in rows_list if row.item_kind == "summary"]

    messages: dict[uuid.UUID, ChatMessage] = {}
    if message_ids:
        msg_result = await session.execute(
            select(ChatMessage).where(ChatMessage.id.in_(message_ids))
        )
        messages = {m.id: m for m in msg_result.scalars().all()}
    summaries: dict[uuid.UUID, LCMSummary] = {}
    if summary_ids:
        summ_result = await session.execute(
            select(LCMSummary).where(LCMSummary.id.in_(summary_ids))
        )
        summaries = {s.id: s for s in summ_result.scalars().all()}

    tokens = _tokenize_query(query)
    out: list[tuple[LCMEmbedding, str, dict[str, object]]] = []
    for row in rows_list:
        meta, excerpt = _excerpt_and_meta(row, messages, summaries, tokens)
        if excerpt is None:
            continue
        out.append((row, excerpt, meta))
    return out


def _excerpt_and_meta(
    row: LCMEmbedding,
    messages: dict[uuid.UUID, ChatMessage],
    summaries: dict[uuid.UUID, LCMSummary],
    tokens: Sequence[str],
) -> tuple[dict[str, object], str | None]:
    """Build the per-row metadata + excerpt for semantic_search."""
    if row.item_kind == "message":
        msg = messages.get(row.item_id)
        if msg is None:
            return {}, None
        meta: dict[str, object] = {
            "ordinal": msg.ordinal,
            "role": msg.role,
        }
        return meta, _excerpt_around(msg.content or "", tokens)
    summary = summaries.get(row.item_id)
    if summary is None:
        return {}, None
    meta = {
        "summary_depth": summary.depth,
        "summary_kind": summary.summary_kind,
    }
    return meta, _excerpt_around(summary.content or "", tokens)
