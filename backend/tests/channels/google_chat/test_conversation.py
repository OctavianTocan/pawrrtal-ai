"""Google Chat channel — persistent per-surface conversation lookup.

The first call creates the channel's ``google_chat`` conversation and the
second reuses it for the same Chat space/thread; an existing
``ChannelBinding`` resolves a user directly (no dev-admin config needed).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import get_user_id_for_external
from app.channels.google_chat.conversation import (
    get_or_create_google_chat_conversation,
    google_chat_conversation_key,
)
from app.channels.google_chat.dev_admin import GOOGLE_CHAT_PROVIDER
from app.infrastructure.database.legacy import User
from app.models import ChannelBinding, Conversation
from tests.channels.google_chat.helpers import OTHER_SENDER, SPACE, THREAD

pytestmark = pytest.mark.anyio


async def test_get_or_create_conversation_creates_then_reuses(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """First call creates a google_chat conversation; the second reuses the scoped row."""
    key = google_chat_conversation_key(space_name=SPACE, thread_name=THREAD)
    first = await get_or_create_google_chat_conversation(
        user_id=test_user.id,
        channel_thread_key=key,
        session=db_session,
    )
    second = await get_or_create_google_chat_conversation(
        user_id=test_user.id,
        channel_thread_key=key,
        session=db_session,
    )

    assert first.id == second.id
    assert first.origin_channel == "google_chat"
    assert first.channel_thread_key == key
    rows = (
        (
            await db_session.execute(
                select(Conversation).where(Conversation.origin_channel == "google_chat")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_same_bound_user_gets_distinct_conversations_per_chat_thread(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """One bound user can talk in separate Chat rooms/threads without mixed history."""
    first_key = google_chat_conversation_key(space_name=SPACE, thread_name=THREAD)
    second_key = google_chat_conversation_key(
        space_name=SPACE,
        thread_name=f"{SPACE}/threads/OTHER",
    )

    first = await get_or_create_google_chat_conversation(
        user_id=test_user.id,
        channel_thread_key=first_key,
        session=db_session,
    )
    second = await get_or_create_google_chat_conversation(
        user_id=test_user.id,
        channel_thread_key=second_key,
        session=db_session,
    )
    second_again = await get_or_create_google_chat_conversation(
        user_id=test_user.id,
        channel_thread_key=second_key,
        session=db_session,
    )

    assert first.id != second.id
    assert second.id == second_again.id
    assert {first.channel_thread_key, second.channel_thread_key} == {first_key, second_key}


async def test_bound_sender_resolves_without_autolink(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """An existing binding resolves directly (no dev-admin config needed)."""
    db_session.add(
        ChannelBinding(
            user_id=test_user.id,
            provider=GOOGLE_CHAT_PROVIDER,
            external_user_id=OTHER_SENDER,
            external_chat_id=SPACE,
            display_handle="someone",
            created_at=datetime.now(),
        )
    )
    await db_session.commit()

    resolved = await get_user_id_for_external(
        provider=GOOGLE_CHAT_PROVIDER,
        external_user_id=OTHER_SENDER,
        session=db_session,
    )
    assert resolved == test_user.id
