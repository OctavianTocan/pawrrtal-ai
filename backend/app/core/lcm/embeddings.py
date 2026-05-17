"""Semantic retrieval + RRF blending for LCM (issue #254).

Lexical search (``lcm_search``) wins on keyword recall but misses
when the user paraphrases.  Semantic-only search has the opposite
failure mode.  This module adds the embedding storage, deterministic
fake-embedder for CI, semantic search routine, and the Reciprocal
Rank Fusion blender that combines the two retrieval signals into a
single ranked list with transparent component scores.

Why a deterministic hash embedder for the default path
------------------------------------------------------
Issue #254 explicitly says live embedding providers must not be
mandatory in CI.  A SHA-256-seeded random vector is enough to:

* return *consistent* embeddings for the same content,
* surface paraphrase-style similarity when the same tokens appear
  in different phrasings (because token hashes contribute to the
  same vector dimensions), and
* keep the test suite fully offline.

A future iteration can swap the default for a real provider by
implementing the same :class:`Embedder` protocol and registering it
behind a config flag - the storage layout, content-hash skip path,
and RRF blender will not change.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tools.lcm_search import (
    LCMSearchResult,
    _excerpt_around,
    _tokenize_query,
    lcm_search,
)
from app.models import ChatMessage, LCMEmbedding, LCMSummary

# Embedding dimensionality.  Small enough to keep test payloads
# trivial; large enough that the cosine-similarity signal is still
# meaningful.  Real provider embeddings are typically 384-1536d -
# the storage layer accepts any length, the deterministic embedder
# uses this constant.
EMBEDDING_DIM = 64

# Identifier persisted on every ``LCMEmbedding.embedding_model``
# column for embeddings produced by the deterministic CI embedder.
# A future provider swap would use its own identifier so historical
# rows stay traceable.
FAKE_MODEL_ID = "pawrrtal-fake-hash-64d"

# Reciprocal Rank Fusion's smoothing constant.  The standard
# literature value is 60; higher values flatten the curve, lower
# values reward top-ranked items more aggressively.  We surface the
# constant so the hybrid blender stays inspectable.
_RRF_SMOOTHING = 60

# Default cap on the number of semantic candidates pulled from the
# DB before scoring.  Same shape as ``lcm_search``'s candidate fetch
# cap; protects against pathological conversations.
_SEMANTIC_CANDIDATE_CAP = 200

# Token tokeniser splits on the same non-alphanumeric boundaries as
# ``lcm_search``; the resulting tokens seed the deterministic vector.
_TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9\-]+")

# Standard deviation of the per-dimension Gaussian noise added to
# each embedding.  Small enough that the token-derived skeleton of
# the vector still dominates similarity.
_NOISE_STDDEV = 0.1

# Numerical tolerance for "this vector is already unit-length";
# below this the cosine helper trusts the magnitudes and skips the
# division by ``mag_a * mag_b``.
_UNIT_VECTOR_TOLERANCE = 1e-6

SearchMode = Literal["lexical", "semantic", "hybrid"]
ItemKind = Literal["message", "summary"]


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


class Embedder(Protocol):
    """Minimal embedder contract used by ingest + semantic search."""

    @property
    def model_id(self) -> str:
        """Identifier persisted on every embedding row."""

    def embed(self, text: str) -> list[float]:
        """Return a unit-length embedding vector for ``text``."""


class DeterministicHashEmbedder:
    """Hash-seeded embedder used in tests + CI.

    For each query/content text, we tokenise the input the same way
    :mod:`app.core.tools.lcm_search` does, hash each token into a
    dimension index, and accumulate a unit vector.  This makes
    semantically-similar paraphrases produce overlapping vectors
    without needing a model server in the loop.

    The implementation is deterministic: same input string in,
    same vector out, every run.
    """

    def __init__(self, *, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim
        self._model_id = FAKE_MODEL_ID

    @property
    def model_id(self) -> str:
        """Persisted identifier of this embedder."""
        return self._model_id

    def embed(self, text: str) -> list[float]:
        """Tokenise + hash each token into a dimension; normalise."""
        if not text:
            return [0.0] * self._dim
        vector = [0.0] * self._dim
        tokens = _TOKEN_PATTERN.findall(text.lower())
        for token in tokens:
            dim_index = _hash_to_dim(token, self._dim)
            # Add a small token-derived value so repeated tokens
            # reinforce the dimension; using a hash-derived sign so
            # unrelated tokens that hit the same dimension can
            # cancel rather than always add.
            sign = _hash_sign(token)
            vector[dim_index] += sign
        # Random component seeded by the full content hash gives
        # paraphrases that share most tokens a strong similarity
        # while letting fully-disjoint content stay distant.  The
        # generator is a deterministic vector source, not a security
        # primitive, so the bandit ``S311`` flag is intentionally
        # silenced - swapping in ``secrets`` would defeat the
        # determinism that makes this embedder CI-safe.
        rng = random.Random(content_hash(text))  # noqa: S311  # nosec B311 - deterministic vector seeding, not crypto
        noise = [rng.gauss(0.0, _NOISE_STDDEV) for _ in range(self._dim)]
        vector = [v + n for v, n in zip(vector, noise, strict=True)]
        return _normalise(vector)


@dataclass(frozen=True)
class SemanticHit:
    """Internal hit shape used while assembling search results."""

    item_kind: ItemKind
    item_id: str
    score: float
    excerpt: str
    metadata: dict[str, object]


def content_hash(text: str) -> str:
    """Stable SHA-256 hash of ``text`` (hex digest)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _hash_to_dim(token: str, dim: int) -> int:
    """Map a token to a dimension index in ``[0, dim)``."""
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dim


def _hash_sign(token: str) -> float:
    """Return +1.0 or -1.0 deterministically based on the token hash."""
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return 1.0 if digest[0] % 2 == 0 else -1.0


def _normalise(vector: list[float]) -> list[float]:
    """L2-normalise ``vector`` so cosine similarity == dot product."""
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude == 0:
        return vector
    return [v / magnitude for v in vector]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity assuming both vectors are unit-length.

    Falls back to a magnitude division for callers that pass
    non-normalised vectors so the function stays robust.
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    if abs(mag_a - 1.0) < _UNIT_VECTOR_TOLERANCE and abs(mag_b - 1.0) < _UNIT_VECTOR_TOLERANCE:
        return dot
    return dot / (mag_a * mag_b)


async def upsert_embedding(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    item_kind: ItemKind,
    item_id: uuid.UUID,
    content: str,
    embedder: Embedder | None = None,
) -> LCMEmbedding | None:
    """Insert or refresh an embedding row for one LCM item.

    Skips empty content (so empty assistant placeholders never get
    embedded as meaningful memory - one of the explicit acceptance
    criteria in #254).  Skips re-embedding when the supplied
    content's hash matches the persisted row's hash.

    Returns the persisted row, or ``None`` when content was empty.
    """
    body = (content or "").strip()
    if not body:
        return None

    used_embedder = embedder or DeterministicHashEmbedder()
    new_hash = content_hash(body)

    existing = await _existing_embedding(
        session,
        conversation_id=conversation_id,
        item_kind=item_kind,
        item_id=item_id,
        embedding_model=used_embedder.model_id,
    )
    if existing is not None and existing.content_hash == new_hash:
        return existing

    vector = used_embedder.embed(body)

    if existing is None:
        row = LCMEmbedding(
            conversation_id=conversation_id,
            item_kind=item_kind,
            item_id=item_id,
            embedding_model=used_embedder.model_id,
            embedding=vector,
            content_hash=new_hash,
        )
        session.add(row)
    else:
        existing.embedding = vector
        existing.content_hash = new_hash
        row = existing
    await session.flush()
    return row


async def _existing_embedding(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    item_kind: str,
    item_id: uuid.UUID,
    embedding_model: str,
) -> LCMEmbedding | None:
    """Lookup helper for the unique tuple."""
    result = await session.execute(
        select(LCMEmbedding).where(
            LCMEmbedding.conversation_id == conversation_id,
            LCMEmbedding.item_kind == item_kind,
            LCMEmbedding.item_id == item_id,
            LCMEmbedding.embedding_model == embedding_model,
        )
    )
    return result.scalar_one_or_none()


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
        result = await session.execute(select(ChatMessage).where(ChatMessage.id.in_(message_ids)))
        messages = {m.id: m for m in result.scalars().all()}
    summaries: dict[uuid.UUID, LCMSummary] = {}
    if summary_ids:
        result = await session.execute(select(LCMSummary).where(LCMSummary.id.in_(summary_ids)))
        summaries = {s.id: s for s in result.scalars().all()}

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
