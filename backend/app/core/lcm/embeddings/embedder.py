"""Embedder protocol + deterministic hash embedder + vector helpers.

The default :class:`DeterministicHashEmbedder` is intentionally
offline + reproducible so CI never needs a live embedding provider
(issue #254 acceptance criterion).  Real providers can implement the
same :class:`Embedder` protocol later without touching the storage
layer or the RRF blender.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections.abc import Sequence
from typing import Literal, Protocol

# Discriminator for which LCM table an embedding row points at.
# Lives in the embedder module so storage / semantic / hybrid can
# all share the alias without producing import cycles.
ItemKind = Literal["message", "summary"]

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
