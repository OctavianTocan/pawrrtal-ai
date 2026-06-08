"""Conversation-owned settings mutations shared by channels and chat."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation
from app.providers.reasoning import ReasoningResolution, resolve_reasoning_effort


async def update_conversation_model(
    *,
    conversation_id: uuid.UUID,
    model_id: str | None,
    session: AsyncSession,
) -> bool:
    """Persist a model-ID override on an existing conversation row."""
    row = await session.get(Conversation, conversation_id)
    if row is None:
        return False
    row.model_id = model_id
    await session.commit()
    return True


async def update_conversation_verbose_level(
    *,
    conversation_id: uuid.UUID,
    verbose_level: int | None,
    session: AsyncSession,
) -> bool:
    """Persist a per-conversation verbose-level override."""
    row = await session.get(Conversation, conversation_id)
    if row is None:
        return False
    row.verbose_level = verbose_level
    await session.commit()
    return True


async def update_conversation_reasoning_effort(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    reasoning_effort: str | None,
    session: AsyncSession,
) -> bool:
    """Persist a per-conversation reasoning-effort override."""
    row = await session.get(Conversation, conversation_id)
    if row is None or row.user_id != user_id:
        return False
    row.reasoning_effort = reasoning_effort
    await session.commit()
    return True


async def normalize_conversation_reasoning_effort(
    *,
    conversation_id: uuid.UUID,
    session: AsyncSession,
    model_id_override: str | None = None,
) -> tuple[ReasoningResolution | None, str | None]:
    """Resolve and persist a conversation reasoning effort against a model."""
    row = await session.get(Conversation, conversation_id)
    if row is None:
        return None, None
    previous_effort: str | None = row.reasoning_effort
    effective_model_id = model_id_override if model_id_override is not None else row.model_id
    resolution = resolve_reasoning_effort(
        model_id=effective_model_id,
        stored_effort=previous_effort,
    )
    if resolution.action in ("adapted", "cleared"):
        row.reasoning_effort = resolution.next_stored
        await session.commit()
    return resolution, previous_effort
