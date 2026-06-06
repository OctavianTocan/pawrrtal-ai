"""Shared fixtures for the Google Chat channel test package.

The expensive shared fixture is :func:`command_ctx` — a ``CommandContext``
backed by a real user + ``google_chat`` conversation over the test DB, used by
the commands, cards, and LCM suites. The per-event builders and constants live
in :mod:`tests.channels.google_chat.helpers`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.google_chat.commands import CommandContext
from app.infrastructure.database.legacy import User
from app.models import Conversation
from tests.channels.google_chat.helpers import DEV_ADMIN_SENDER


@pytest.fixture
async def command_ctx(db_session: AsyncSession) -> CommandContext:
    """A CommandContext backed by a real user + google_chat conversation."""
    user = User(
        id=uuid4(),
        email=f"cmd-{uuid4()}@pawrrtal.dev",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    conversation = Conversation(
        id=uuid4(),
        user_id=user.id,
        title="Google Chat",
        origin_channel="google_chat",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return CommandContext(
        user_id=user.id,
        conversation=conversation,
        args="",
        sender_resource=DEV_ADMIN_SENDER,
        sender_email="cmd@pawrrtal.dev",
        session=db_session,
    )
