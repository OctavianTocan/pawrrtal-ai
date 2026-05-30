"""Dreaming background-reflection ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from app.infrastructure.models.base import Base
from app.infrastructure.models.common import utcnow


class DreamingJob(Base):
    """One run of the between-sessions reflection pass (#341).

    Per the ADR at
    ``frontend/content/docs/handbook/decisions/2026-05-20-dreaming-background-reflection.mdx``,
    the pass runs in two modes:

    * ``session_end`` — single conversation after idle window.
    * ``daily_rollup`` — user-scoped reflection over prior 24h.

    Each row records the inputs (model, token counts), the outputs
    (counts per category + session_summary), and the lifecycle
    (status + timestamps + error_text). The dreaming pass writes
    memory rows with ``source="dreaming"`` and
    ``provenance_job_id=<this row's id>`` so any consolidated
    memory can be traced back to the pass that produced it.
    """

    __tablename__ = "dreaming_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    # ``session_end`` | ``daily_rollup``. Pinned by
    # ``ck_dreaming_jobs_scope_valid`` in migration 025.
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    # ``pending`` | ``running`` | ``completed`` | ``failed``.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    memories_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    patterns_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    followups_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["DreamingJob"]
