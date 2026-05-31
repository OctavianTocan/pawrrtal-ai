"""Regression tests for the chat_message CRUD helpers.

The chat sidebar orders conversations by ``Conversation.updated_at DESC``.
For a long time the helpers only bumped ``ChatMessage.updated_at`` and
left the parent untouched, so messages from Telegram (and second+ turns
from web) never re-sorted the sidebar.  These tests pin the fix.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.messages_crud import (
    append_assistant_placeholder,
    append_user_message,
    fail_stale_streaming_messages,
    finalize_assistant_message,
)
from app.infrastructure.database.legacy import User
from app.models import Conversation


async def _make_conversation(session: AsyncSession, user: User, *, when: datetime) -> Conversation:
    """Insert a conversation row with a fixed ``updated_at`` so we can compare."""
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="Test",
        created_at=when,
        updated_at=when,
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


@pytest.mark.anyio
async def test_append_user_message_bumps_conversation_updated_at(
    db_session: AsyncSession, test_user: User
) -> None:
    """A new user message must bubble the conversation to the sidebar top."""
    old = datetime(2025, 1, 1)
    conv = await _make_conversation(db_session, test_user, when=old)

    await append_user_message(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        content="hello",
    )
    await db_session.commit()
    await db_session.refresh(conv)

    assert conv.updated_at > old


@pytest.mark.anyio
async def test_fail_stale_streaming_messages_marks_old_placeholders_failed(
    db_session: AsyncSession, test_user: User
) -> None:
    """Startup repair makes interrupted assistant turns visible instead of stuck."""
    old = datetime(2025, 1, 1)
    conv = await _make_conversation(db_session, test_user, when=old)
    placeholder = await append_assistant_placeholder(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
    )
    placeholder.updated_at = old
    db_session.add(placeholder)
    await db_session.commit()

    repaired = await fail_stale_streaming_messages(
        db_session,
        older_than=timedelta(seconds=30),
        reason="interrupted",
    )
    await db_session.commit()
    await db_session.refresh(placeholder)

    assert repaired == 1
    assert placeholder.assistant_status == "failed"
    assert placeholder.content == "interrupted"


@pytest.mark.anyio
async def test_finalize_assistant_message_bumps_conversation_updated_at(
    db_session: AsyncSession, test_user: User
) -> None:
    """Finalising the assistant turn also re-stamps the parent conversation.

    Without this a long stream that started before another conversation's
    quick turn would let the slower one sink down the list once it finished.
    """
    old = datetime(2025, 1, 1)
    conv = await _make_conversation(db_session, test_user, when=old)

    await append_user_message(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        content="hi",
    )
    placeholder = await append_assistant_placeholder(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
    )
    await db_session.commit()

    # Reset updated_at to an older value so we can isolate the finalize bump.
    conv.updated_at = old
    db_session.add(conv)
    await db_session.commit()

    await finalize_assistant_message(
        db_session,
        message_id=placeholder.id,
        content="hello back",
        thinking=None,
        tool_calls=None,
        timeline=None,
        thinking_duration_seconds=None,
        assistant_status="complete",
    )
    await db_session.commit()
    await db_session.refresh(conv)

    assert conv.updated_at > old
