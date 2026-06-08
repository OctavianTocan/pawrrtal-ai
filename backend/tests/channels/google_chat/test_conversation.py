"""Google Chat channel — persistent per-user conversation (conversation + crud).

The first call creates the channel's ``google_chat`` conversation and the
second reuses it; an existing ``ChannelBinding`` resolves a user directly
(no dev-admin config needed).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import get_user_id_for_external
from app.channels.google_chat.conversation import get_or_create_google_chat_conversation
from app.channels.google_chat.dev_admin import GOOGLE_CHAT_PROVIDER
from app.infrastructure.database.legacy import User
from app.models import ChannelBinding, Conversation
from tests.channels.google_chat.helpers import OTHER_SENDER, SPACE

pytestmark = pytest.mark.anyio


async def test_get_or_create_conversation_creates_then_reuses(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """First call creates a google_chat conversation; the second reuses it."""
    first = await get_or_create_google_chat_conversation(user_id=test_user.id, session=db_session)
    second = await get_or_create_google_chat_conversation(user_id=test_user.id, session=db_session)

    assert first.id == second.id
    assert first.origin_channel == "google_chat"
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
