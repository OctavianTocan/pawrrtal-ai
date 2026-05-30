"""CRUD operations for the ChatMessage sidecar table.

The chat endpoint writes one ChatMessage row per logical turn (user prompt
plus assistant placeholder), then patches the assistant row at stream end.
The /messages endpoint reads from this table to rehydrate the chat UI with
full chain-of-thought state.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.models import ChatMessage, Conversation


def _now() -> datetime:
    """Naive UTC timestamp — matches the ``DateTime`` column type used elsewhere."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _touch_conversation(
    session: AsyncSession, conversation_id: uuid.UUID, when: datetime
) -> None:
    """Bump ``Conversation.updated_at`` so the conversation list re-sorts.

    The chat sidebar orders conversations by ``Conversation.updated_at
    DESC``.  Without this every Telegram-originated turn (and indeed every
    web turn after the first) leaves the conversation row untouched, so
    new activity never bubbles to the top.
    """
    await session.execute(
        update(Conversation).where(Conversation.id == conversation_id).values(updated_at=when)
    )


async def get_messages_for_conversation(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    limit: int | None = None,
) -> list[ChatMessage]:
    """Return chat messages for a conversation in insertion order.

    Ordering is by `ordinal` rather than `created_at` so a regenerate that
    overwrites an existing row in place stays in the same slot, which keeps
    the rendered list stable.

    Args:
        session: Async database session.
        conversation_id: Conversation to query.
        limit: If given, return only the most recent *limit* messages.
            Useful for capping the context window sent to the LLM.
    """
    if limit is not None:
        # Fetch the tail (DESC + LIMIT), then reverse in Python so the
        # caller still receives rows in ascending ordinal order.
        result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.ordinal.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return rows
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.ordinal.asc())
    )
    return list(result.scalars().all())


async def _next_ordinal(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    """Return the next free ordinal for a conversation, starting at 0."""
    result = await session.execute(
        select(func.max(ChatMessage.ordinal)).where(ChatMessage.conversation_id == conversation_id)
    )
    current_max = result.scalar()
    return 0 if current_max is None else current_max + 1


async def append_user_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
) -> ChatMessage:
    """Insert a new user message at the end of the conversation.

    Bumps ``Conversation.updated_at`` so the chat list re-sorts on the
    next read — messages from every surface (web, Electron, Telegram)
    must bubble the conversation to the top.
    """
    now = _now()
    message = ChatMessage(
        conversation_id=conversation_id,
        user_id=user_id,
        ordinal=await _next_ordinal(session, conversation_id),
        role="user",
        content=content,
        created_at=now,
        updated_at=now,
    )
    session.add(message)
    await session.flush()
    await _touch_conversation(session, conversation_id, now)
    return message


async def append_assistant_placeholder(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ChatMessage:
    """Insert an empty assistant row that the streaming loop will patch in place."""
    now = _now()
    message = ChatMessage(
        conversation_id=conversation_id,
        user_id=user_id,
        ordinal=await _next_ordinal(session, conversation_id),
        role="assistant",
        content="",
        assistant_status="streaming",
        created_at=now,
        updated_at=now,
    )
    session.add(message)
    await session.flush()
    return message


async def finalize_assistant_message(
    session: AsyncSession,
    *,
    message_id: uuid.UUID,
    content: str,
    thinking: str | None,
    tool_calls: list[dict[str, Any]] | None,
    timeline: list[dict[str, Any]] | None,
    thinking_duration_seconds: int | None,
    assistant_status: str,
) -> None:
    """Update the assistant row with the final stream state.

    Called both on successful completion (``status="complete"``) and on
    stream-level errors (``status="failed"``) so the row always reflects the
    most recent state visible to the user.

    Also bumps the parent ``Conversation.updated_at`` so the sidebar
    re-sorts when the assistant's reply finishes (a long stream that
    started seconds ago shouldn't sink the conversation back down).
    """
    now = _now()
    await session.execute(
        update(ChatMessage)
        .where(ChatMessage.id == message_id)
        .values(
            content=content,
            thinking=thinking,
            tool_calls=tool_calls,
            timeline=timeline,
            thinking_duration_seconds=thinking_duration_seconds,
            assistant_status=assistant_status,
            updated_at=now,
        )
    )
    # finalize_assistant_message receives a message_id not a conversation_id,
    # so look up the conversation via the row we just touched.
    result = await session.execute(
        select(ChatMessage.conversation_id).where(ChatMessage.id == message_id)
    )
    conversation_id = result.scalar_one_or_none()
    if conversation_id is not None:
        await _touch_conversation(session, conversation_id, now)
