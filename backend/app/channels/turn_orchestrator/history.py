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
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import async_session_maker
from app.lcm import assemble_context as lcm_assemble_context
from app.lcm import ingest_message as lcm_ingest_message

from .types import ChatTurnInput

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _load_history_and_persist(
    turn_input: ChatTurnInput,
) -> tuple[list[dict[str, str]], uuid.UUID]:
    """Read recent history, then persist the current user turn and placeholder.

    When ``settings.lcm_enabled`` is ``True``, the history slice is
    assembled from the LCM context list (``lcm_context_items``) so that
    compacted summaries are visible to the provider, and both the user
    turn and assistant placeholder are ingested into the LCM context
    list before the stream starts.  When LCM is off the behaviour is
    unchanged — a raw ``LIMIT history_window`` query over
    ``chat_messages``.
    """
    async with _turn_session(turn_input) as session:
        if settings.lcm_enabled:
            history = await lcm_assemble_context(
                session,
                conversation_id=turn_input.conversation_id,
                fresh_tail_count=settings.lcm_fresh_tail_count,
            )
        else:
            recent_rows = await get_messages_for_conversation(
                session,
                turn_input.conversation_id,
                limit=turn_input.history_window,
            )
            history = [
                {"role": row.role, "content": row.content or ""}
                for row in recent_rows
                if row.role in {"user", "assistant"}
            ]
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
        if settings.lcm_enabled:
            await lcm_ingest_message(
                session,
                conversation_id=turn_input.conversation_id,
                message_id=user_msg.id,
            )
            await lcm_ingest_message(
                session,
                conversation_id=turn_input.conversation_id,
                message_id=assistant_row.id,
            )
        await session.commit()
        return history, assistant_row.id


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
