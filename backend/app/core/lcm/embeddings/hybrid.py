"""Hybrid lexical + semantic retrieval via Reciprocal Rank Fusion.

Lexical search (``lcm_search``) wins on keyword recall but misses
when the user paraphrases.  Semantic-only search has the opposite
failure mode.  This module blends both signals into a single ranked
list with transparent component scores so callers can inspect *why*
an item won, not just that it did.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm.embeddings.embedder import Embedder, ItemKind
from app.core.lcm.embeddings.semantic import SemanticHit, semantic_search
from app.core.tools.lcm_search import LCMSearchResult, lcm_search

# Reciprocal Rank Fusion's smoothing constant.  The standard
# literature value is 60; higher values flatten the curve, lower
# values reward top-ranked items more aggressively.  We surface the
# constant so the hybrid blender stays inspectable.
_RRF_SMOOTHING = 60

SearchMode = Literal["lexical", "semantic", "hybrid"]


class LCMHybridSearchResult(TypedDict):
    """One ranked hit from hybrid lexical + semantic retrieval.

    Mirrors the shape proposed in issue #254 so a future swap of
    either retrieval leg is API-stable.
    """

    item_kind: ItemKind
    item_id: str
    final_score: float
    lexical_rank: int | None
    lexical_score: float | None
    semantic_rank: int | None
    semantic_score: float | None
    rrf_score: float
    excerpt: str
    metadata: dict[str, object]


def reciprocal_rank_fusion(
    *,
    lexical: Sequence[LCMSearchResult],
    semantic: Sequence[SemanticHit],
) -> list[LCMHybridSearchResult]:
    """Blend lexical + semantic rankings with Reciprocal Rank Fusion.

    Each entry contributes ``1 / (k + rank)`` to its item's final
    score.  Component ranks and scores are preserved on every result
    so callers can inspect *why* an item won, not just that it did.
    """
    blended: dict[str, LCMHybridSearchResult] = {}
    for index, lex in enumerate(lexical):
        item_id = lex["item_id"]
        rank = index + 1
        rrf_term = 1.0 / (_RRF_SMOOTHING + rank)
        blended[item_id] = _start_blend_from_lexical(lex, rank=rank, rrf_term=rrf_term)
    for index, sem in enumerate(semantic):
        rank = index + 1
        rrf_term = 1.0 / (_RRF_SMOOTHING + rank)
        item_id = sem.item_id
        if item_id in blended:
            blended[item_id]["semantic_rank"] = rank
            blended[item_id]["semantic_score"] = sem.score
            blended[item_id]["rrf_score"] = blended[item_id]["rrf_score"] + rrf_term
        else:
            blended[item_id] = _start_blend_from_semantic(sem, rank=rank, rrf_term=rrf_term)
    for entry in blended.values():
        entry["final_score"] = round(entry["rrf_score"], 6)
    out = list(blended.values())
    out.sort(key=lambda r: -r["final_score"])
    return out


def _start_blend_from_lexical(
    result: LCMSearchResult,
    *,
    rank: int,
    rrf_term: float,
) -> LCMHybridSearchResult:
    """Build the initial hybrid entry seeded from a lexical hit."""
    metadata: dict[str, object] = {
        "ordinal": result["ordinal"],
        "role": result["role"],
        "summary_depth": result["summary_depth"],
        "summary_kind": result["summary_kind"],
        "source_ids": result["source_ids"],
    }
    return LCMHybridSearchResult(
        item_kind=result["item_kind"],
        item_id=result["item_id"],
        final_score=0.0,
        lexical_rank=rank,
        lexical_score=result["score"],
        semantic_rank=None,
        semantic_score=None,
        rrf_score=rrf_term,
        excerpt=result["excerpt"],
        metadata=metadata,
    )


def _start_blend_from_semantic(
    hit: SemanticHit,
    *,
    rank: int,
    rrf_term: float,
) -> LCMHybridSearchResult:
    """Build the initial hybrid entry seeded from a semantic-only hit."""
    return LCMHybridSearchResult(
        item_kind=hit.item_kind,
        item_id=hit.item_id,
        final_score=0.0,
        lexical_rank=None,
        lexical_score=None,
        semantic_rank=rank,
        semantic_score=hit.score,
        rrf_score=rrf_term,
        excerpt=hit.excerpt,
        metadata=hit.metadata,
    )


async def lcm_hybrid_search(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    query: str,
    limit: int = 8,
    mode: SearchMode = "hybrid",
    embedder: Embedder | None = None,
) -> list[LCMHybridSearchResult]:
    """Public retrieval entry point with mode toggle.

    * ``mode="lexical"``  - only the :func:`lcm_search` ranking,
      semantic legs left null in each result.
    * ``mode="semantic"`` - only the cosine-similarity ranking,
      lexical legs left null in each result.
    * ``mode="hybrid"``   - both, blended with Reciprocal Rank
      Fusion; final score order respects both signals.
    """
    lexical: list[LCMSearchResult] = []
    semantic: list[SemanticHit] = []
    if mode in ("lexical", "hybrid"):
        lexical = list(
            await lcm_search(
                session,
                conversation_id=conversation_id,
                query=query,
                limit=limit,
            )
        )
    if mode in ("semantic", "hybrid"):
        semantic = await semantic_search(
            session,
            conversation_id=conversation_id,
            query=query,
            limit=limit,
            embedder=embedder,
        )
    blended = reciprocal_rank_fusion(lexical=lexical, semantic=semantic)
    return blended[:limit]
