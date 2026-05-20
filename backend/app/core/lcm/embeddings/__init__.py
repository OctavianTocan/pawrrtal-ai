"""Semantic retrieval + RRF blending for LCM (issue #254).

Lexical search (``lcm_search``) wins on keyword recall but misses
when the user paraphrases.  Semantic-only search has the opposite
failure mode.  This package adds the embedding storage, deterministic
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

Module layout
-------------
The package keeps each retrieval role in its own module:

* :mod:`.embedder` — :class:`Embedder` protocol, the deterministic
  :class:`DeterministicHashEmbedder`, hash/vector math
  (:func:`content_hash`, :func:`cosine_similarity`), and the shared
  :data:`ItemKind` alias.
* :mod:`.storage` — :func:`upsert_embedding` against
  :class:`~app.models.LCMEmbedding`.
* :mod:`.semantic` — :class:`SemanticHit` + :func:`semantic_search`
  (cosine similarity over stored embedding rows).
* :mod:`.hybrid` — :class:`LCMHybridSearchResult`, :data:`SearchMode`,
  :func:`reciprocal_rank_fusion`, and the :func:`lcm_hybrid_search`
  entry point.
"""

from __future__ import annotations

from app.core.lcm.embeddings.embedder import (
    EMBEDDING_DIM,
    DeterministicHashEmbedder,
    Embedder,
    ItemKind,
    content_hash,
    cosine_similarity,
)
from app.core.lcm.embeddings.hybrid import (
    LCMHybridSearchResult,
    SearchMode,
    lcm_hybrid_search,
    reciprocal_rank_fusion,
)
from app.core.lcm.embeddings.semantic import SemanticHit, semantic_search
from app.core.lcm.embeddings.storage import upsert_embedding

__all__ = [
    "EMBEDDING_DIM",
    "DeterministicHashEmbedder",
    "Embedder",
    "ItemKind",
    "LCMHybridSearchResult",
    "SearchMode",
    "SemanticHit",
    "content_hash",
    "cosine_similarity",
    "lcm_hybrid_search",
    "reciprocal_rank_fusion",
    "semantic_search",
    "upsert_embedding",
]
