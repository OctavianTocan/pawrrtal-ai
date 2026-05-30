"""Proactive memory ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from app.infrastructure.models.base import Base
from app.infrastructure.models.common import utcnow


class Memory(Base):
    """A typed proactive memory written by the post-turn classifier or dreaming pass.

    Per the ADR at
    ``frontend/content/docs/handbook/decisions/2026-05-20-proactive-memory-updates.mdx``,
    the chat router runs a post-turn classifier that captures user
    preferences, project decisions, and explicit feedback. Each
    captured signal becomes a row here, typed by ``kind``.

    The dreaming pass (#341) reuses the same table — ``source`` is
    the provenance discriminator (``classifier`` / ``dreaming`` /
    ``user``) and ``provenance_job_id`` ties dreaming-written rows
    back to the job that wrote it.
    """

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # One of ``feedback`` / ``project`` / ``user``. Pinned to that
    # set by ``ck_memories_kind_valid`` in migration 024.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # ``classifier`` (per-turn) | ``dreaming`` (between-sessions) |
    # ``user`` (manual). Pinned by ``ck_memories_source_valid``.
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="classifier", server_default="classifier"
    )
    # Set when ``source == "dreaming"`` — ties the row back to the
    # ``DreamingJob`` that wrote it (table introduced by #341).
    provenance_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Opaque bytes; the existing ``lcm/embeddings.py`` pipeline does
    # the per-provider serialisation. Promoted to ``pgvector`` later.
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_referenced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


__all__ = ["Memory"]
