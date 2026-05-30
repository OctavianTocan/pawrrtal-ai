"""CRUD operations for proactive memory rows (#340).

The schema lives in migration 024 and the ORM model in
:mod:`app.models`. This module owns the small surface every
consumer (the post-turn classifier hook, the ``memory_query``
tool, the system-prompt assembler) shares: insert with dedupe,
read top-K for system-prompt grounding, mark a memory as
referenced when the model actually used it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory

MemoryKind = Literal["feedback", "project", "user"]
MemorySource = Literal["classifier", "dreaming", "user"]

_DEDUPE_SUBSTRING_MAX_LEN = 120


async def insert_memory(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: MemoryKind,
    text: str,
    source: MemorySource = "classifier",
    workspace_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    source_message_id: uuid.UUID | None = None,
    provenance_job_id: uuid.UUID | None = None,
    embedding: bytes | None = None,
) -> Memory:
    """Persist a new memory row and return the saved ORM instance.

    The caller is expected to have already checked for duplicates
    (see :func:`find_similar_memories`). The dedupe step lives in
    the classifier / dreaming pipelines, not here, so each consumer
    can pick its own similarity threshold.
    """
    row = Memory(
        id=uuid.uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        kind=kind,
        source=source,
        provenance_job_id=provenance_job_id,
        text=text,
        embedding=embedding,
        source_message_id=source_message_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_memories_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: MemoryKind | None = None,
    limit: int = 20,
) -> list[Memory]:
    """Read recent memories for ``user_id``, newest first.

    Used by the system-prompt assembler to surface top-K rows. The
    ``kind`` filter lets the assembler pull the three buckets
    separately so they can be formatted differently in the prompt
    (preferences as bullet points, project decisions as inline
    statements, etc.).
    """
    stmt = select(Memory).where(Memory.user_id == user_id)
    if kind is not None:
        stmt = stmt.where(Memory.kind == kind)
    stmt = stmt.order_by(Memory.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_similar_memories(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    text: str,
    kind: MemoryKind,
    limit: int = 5,
) -> list[Memory]:
    """Return memories whose text matches ``text`` via case-insensitive substring.

    This is the cheap pre-dedupe filter — full embedding cosine
    similarity lives in a separate helper to be added by the
    classifier PR. For now, substring covers the most common
    "I just wrote the same observation" case (the classifier tends
    to emit short, deterministic statements that share substrings
    when restating the same fact).
    """
    escaped = text[:_DEDUPE_SUBSTRING_MAX_LEN].replace("%", r"\%").replace("_", r"\_")
    stmt = (
        select(Memory)
        .where(Memory.user_id == user_id)
        .where(Memory.kind == kind)
        .where(Memory.text.ilike(f"%{escaped}%", escape="\\"))
        .order_by(Memory.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_memory_referenced(
    session: AsyncSession,
    memory_id: uuid.UUID,
) -> None:
    """Touch ``last_referenced_at`` so future cleanup jobs can keep hot rows.

    Called by the ``memory_query`` tool whenever the model actually
    surfaces a memory in its turn. Pure timestamp write; the row
    object isn't returned because every caller today is
    fire-and-forget.
    """
    row = await session.get(Memory, memory_id)
    if row is None:
        return
    row.last_referenced_at = datetime.now(UTC)
    await session.commit()
