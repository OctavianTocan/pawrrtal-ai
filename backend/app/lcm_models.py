"""ORM models for the LCM (large context model) retrieval substrate.

Extracted from :mod:`app.models` to keep that module under the 500-line
file budget. Mirrors the precedent of :mod:`app.governance_models` and
:mod:`app.mcp_models` — the parent re-exports each class so existing
``from app.models import LCMSummary`` imports keep working.

Tables defined here:

- ``lcm_summaries`` — leaf + condensed summary nodes per conversation.
- ``lcm_summary_sources`` — edges from a summary to the messages or
  summaries it condensed.
- ``lcm_context_items`` — ordered assembled-context list per
  conversation that the chat router walks each turn.
- ``lcm_embeddings`` — per-item vector index for hybrid retrieval.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from .db_base import Base


def _utcnow() -> datetime:
    """Timezone-aware UTC now.

    Mirrors :func:`app.models._utcnow`. Defined locally instead of imported
    from ``app.models`` because ``app.models`` re-exports the LCM classes
    from this module — importing the helper across that boundary creates
    a partial-init circular reference whenever a caller does
    ``from app.lcm_models import LCMSummary`` directly. Matches the
    ``mcp_models.py`` pattern.
    """
    return datetime.now(UTC)


class LCMSummary(Base):
    """A single LCM summary node — either a leaf or a condensed parent."""

    __tablename__ = "lcm_summaries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 0 = leaf (summarises raw messages); 1+ = condensed (summarises other
    # summaries at depth-1).  Used by the condensation pass to decide which
    # nodes are eligible for the next level up.
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The actual summary prose the model produced.
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Approximate token count of ``content`` — cached so the assembly + budget
    # math doesn't have to re-tokenise on every turn.
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Which model produced this summary (e.g. ``gemini-2.5-flash-preview-05-20``).
    # Stored so future re-compaction can pick a stronger model if needed.
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # "normal" | "aggressive" | "fallback" — mirrors the three-level escalation
    # used by the upstream plugin: normal prompt first, aggressive if the
    # output is too large, deterministic truncation if both LLM passes fail.
    summary_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LCMSummarySource(Base):
    """Edge from an :class:`LCMSummary` to one of its source items.

    A source is either a :class:`ChatMessage` (when the parent is a leaf
    summary) or another :class:`LCMSummary` (when the parent is a condensed
    summary).  ``source_kind`` discriminates between the two so a single
    join + filter recovers either flavour.
    """

    __tablename__ = "lcm_summary_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    summary_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("lcm_summaries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "message" | "summary" — string discriminator so the FK can target either.
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # Position in the original ordering so re-assembly is deterministic.
    source_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class LCMContextItem(Base):
    """One entry in the assembled context list for a conversation.

    Walking this table in ``ordinal`` order produces the sequence of items
    fed to the provider every turn.  Each row points at either a raw
    :class:`ChatMessage` or a compacted :class:`LCMSummary`; the chat
    router resolves the actual content at assembly time.

    Compaction rewrites this list in place: a contiguous range of
    ``item_kind="message"`` rows is replaced by a single
    ``item_kind="summary"`` row, and the ordinals are renumbered so the
    list stays dense.
    """

    __tablename__ = "lcm_context_items"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "ordinal",
            name="uq_lcm_context_items_conv_ordinal",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Position in the assembled list.  Gaps are harmless; ingest_message
    # uses max(ordinal)+1 so no dense renumbering after compaction.
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # "message" | "summary" — the discriminator the assembly step uses to
    # decide which lookup to perform.
    item_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # FK target into either chat_messages or lcm_summaries depending on
    # ``item_kind``.  Cascades happen via the parent conversation_id FK.
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LCMEmbedding(Base):
    """Vector index entry for a single LCM-searchable item.

    Issue #254 (hybrid retrieval) needs a place to store one embedding
    per ``ChatMessage`` or ``LCMSummary`` so semantic search can run
    alongside the lexical scorer.  We keep the vectors as JSON arrays
    rather than introducing a pgvector dependency; that decision is
    documented in the issue and revisitable if production workloads
    demand it.  The ``content_hash`` column lets ingest skip
    re-embedding unchanged content; the ``UniqueConstraint`` ensures
    we only ever have one embedding per ``(conversation_id, item_kind,
    item_id, embedding_model)`` tuple.
    """

    __tablename__ = "lcm_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "item_kind",
            "item_id",
            "embedding_model",
            name="uq_lcm_embeddings_conv_kind_item_model",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "message" | "summary" - mirrors LCMContextItem.item_kind so a
    # search hit can be joined back to either source table.
    item_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # Identifier of the embedding provider that produced this vector.
    # Stored so a future migration to a stronger model can re-embed
    # in place without dropping the table.
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    # The embedding itself - stored as a JSON array of floats.  Length
    # is fixed per ``embedding_model`` but the database does not
    # enforce that; the ingest pipeline checks it.
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    # Content hash used to skip re-embedding when the underlying text
    # has not changed.  SHA-256 hex digest of the embedded text.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


__all__ = [
    "LCMContextItem",
    "LCMEmbedding",
    "LCMSummary",
    "LCMSummarySource",
]
