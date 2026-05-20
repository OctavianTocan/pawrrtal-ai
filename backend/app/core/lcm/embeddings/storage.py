"""Embedding persistence: upsert + lookup against ``LCMEmbedding``.

Storage is unaware of how the vector was produced; it only relies on
the :class:`~app.core.lcm.embeddings.embedder.Embedder` protocol and
the content-hash skip path described in issue #254.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm.embeddings.embedder import (
    DeterministicHashEmbedder,
    Embedder,
    ItemKind,
    content_hash,
)
from app.models import LCMEmbedding


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
        # Bump updated_at so downstream auditors can see which rows
        # were re-embedded - the column would otherwise pin to the
        # original creation timestamp forever (Greptile P2 review).
        existing.updated_at = datetime.now(UTC)
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
