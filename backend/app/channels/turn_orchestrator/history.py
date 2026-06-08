"""Conversation history loading and user/placeholder persistence."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from app.channels._turn_workspace import workspace_system_prompt
from app.conversations.messages_crud import (
    append_assistant_placeholder,
    append_user_message,
    get_messages_for_conversation,
)
from app.infrastructure.database.legacy import async_session_maker
from app.plugins.adapters.conversation_memory import (
    ConversationMemoryBackend,
    resolve_conversation_memory,
)

from .types import ChatTurnInput

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _load_history_and_persist(
    turn_input: ChatTurnInput,
) -> tuple[list[dict[str, str]], uuid.UUID]:
    """Read recent history, then persist the current user turn and placeholder."""
    memory = resolve_conversation_memory(workspace_root=turn_input.workspace_root)
    memory_backend = memory.backend if memory is not None else None
    async with _turn_session(turn_input) as session:
        history = await _load_provider_history(
            session=session,
            turn_input=turn_input,
            memory_backend=memory_backend,
        )
        user_msg = await append_user_message(
            session,
            conversation_id=turn_input.conversation_id,
            user_id=turn_input.user_id,
            content=turn_input.question,
        )
        assistant_row = await append_assistant_placeholder(
            session,
            conversation_id=turn_input.conversation_id,
            user_id=turn_input.user_id,
        )
        if memory_backend is not None:
            await memory_backend.ingest_messages(
                session,
                conversation_id=turn_input.conversation_id,
                user_message_id=user_msg.id,
                assistant_message_id=assistant_row.id,
            )
        await session.commit()
        return history, assistant_row.id


async def _load_provider_history(
    *,
    session: AsyncSession,
    turn_input: ChatTurnInput,
    memory_backend: ConversationMemoryBackend | None,
) -> list[dict[str, str]]:
    """Load plugin memory history or fall back to raw message history."""
    if memory_backend is not None:
        history = await memory_backend.load_history(
            session,
            conversation_id=turn_input.conversation_id,
            history_window=turn_input.history_window,
        )
        if history is not None:
            return history
    return await _load_raw_history(session=session, turn_input=turn_input)


async def _load_raw_history(
    *,
    session: AsyncSession,
    turn_input: ChatTurnInput,
) -> list[dict[str, str]]:
    """Load raw user and assistant messages from the conversation."""
    recent_rows = await get_messages_for_conversation(
        session,
        turn_input.conversation_id,
        limit=turn_input.history_window,
    )
    return [
        {"role": row.role, "content": row.content or ""}
        for row in recent_rows
        if row.role in {"user", "assistant"}
    ]


@asynccontextmanager
async def _turn_session(turn_input: ChatTurnInput) -> AsyncIterator[AsyncSession]:
    """Yield the request session when provided, otherwise open a runner session."""
    if turn_input.db_session is not None:
        yield turn_input.db_session
        return
    async with async_session_maker() as session:
        yield session


def _workspace_system_prompt(workspace_root: Path | None) -> str | None:
    """Compatibility wrapper for tests and older internal imports."""
    return workspace_system_prompt(workspace_root)
