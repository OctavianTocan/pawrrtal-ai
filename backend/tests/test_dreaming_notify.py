"""Tests for the Telegram dreaming-completion notifier (#341)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import DreamingCompletedEvent
from app.db import User
from app.integrations.telegram.dreaming_notify import DreamingNotificationService
from app.models import ChannelBinding


async def _seed_telegram_binding(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    external_user_id: str,
) -> None:
    """Insert a telegram binding row for ``user_id``."""
    db_session.add(
        ChannelBinding(
            id=uuid4(),
            user_id=user_id,
            provider="telegram",
            external_user_id=external_user_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await db_session.commit()


@pytest.mark.anyio
async def test_completed_event_with_memories_sends_telegram_dm(
    db_session: AsyncSession, test_user: User
) -> None:
    """A completed pass that wrote memories pushes a notice to the bound Telegram DM."""
    await _seed_telegram_binding(db_session, user_id=test_user.id, external_user_id="987654")
    bot = AsyncMock()
    service = DreamingNotificationService(telegram_bot=bot)
    event = DreamingCompletedEvent(
        job_id=uuid4(),
        user_id=test_user.id,
        conversation_id=uuid4(),
        scope="session_end",
        status="completed",
        memories_written=2,
        patterns_written=1,
        followups_written=0,
        session_summary="Brief reflection on the recent conversation.",
    )

    with patch(
        "app.integrations.telegram.dreaming_notify.async_session_maker",
        _session_factory_returning(db_session),
    ):
        await service.handle_completion(event)

    bot.send_message.assert_awaited_once()
    call = bot.send_message.await_args
    assert call.kwargs["chat_id"] == 987654
    text = call.kwargs["text"]
    assert "Pawrrtal dreamed" in text
    assert "2 new memories" in text
    assert "Brief reflection" in text


@pytest.mark.anyio
async def test_failed_event_does_not_notify(db_session: AsyncSession, test_user: User) -> None:
    """Failed jobs are silent — the user shouldn't be paged on a background error."""
    await _seed_telegram_binding(db_session, user_id=test_user.id, external_user_id="987654")
    bot = AsyncMock()
    service = DreamingNotificationService(telegram_bot=bot)
    event = DreamingCompletedEvent(
        job_id=uuid4(),
        user_id=test_user.id,
        scope="session_end",
        status="failed",
        memories_written=0,
    )

    with patch(
        "app.integrations.telegram.dreaming_notify.async_session_maker",
        _session_factory_returning(db_session),
    ):
        await service.handle_completion(event)

    assert bot.send_message.await_count == 0


@pytest.mark.anyio
async def test_completed_event_with_zero_memories_does_not_notify(
    db_session: AsyncSession, test_user: User
) -> None:
    """A pass where dedupe filtered every candidate stays silent."""
    await _seed_telegram_binding(db_session, user_id=test_user.id, external_user_id="987654")
    bot = AsyncMock()
    service = DreamingNotificationService(telegram_bot=bot)
    event = DreamingCompletedEvent(
        job_id=uuid4(),
        user_id=test_user.id,
        scope="session_end",
        status="completed",
        memories_written=0,
        patterns_written=2,
    )

    with patch(
        "app.integrations.telegram.dreaming_notify.async_session_maker",
        _session_factory_returning(db_session),
    ):
        await service.handle_completion(event)

    assert bot.send_message.await_count == 0


@pytest.mark.anyio
async def test_unbound_user_does_not_notify(db_session: AsyncSession, test_user: User) -> None:
    """Users without a Telegram binding don't see the notice (by design)."""
    bot = AsyncMock()
    service = DreamingNotificationService(telegram_bot=bot)
    event = DreamingCompletedEvent(
        job_id=uuid4(),
        user_id=test_user.id,
        scope="session_end",
        status="completed",
        memories_written=1,
    )

    with patch(
        "app.integrations.telegram.dreaming_notify.async_session_maker",
        _session_factory_returning(db_session),
    ):
        await service.handle_completion(event)

    assert bot.send_message.await_count == 0


@pytest.mark.anyio
async def test_no_bot_handle_is_a_silent_noop() -> None:
    """Without a bot instance the handler returns cleanly — no exception, no work."""
    service = DreamingNotificationService(telegram_bot=None)
    event = DreamingCompletedEvent(
        job_id=uuid4(),
        user_id=uuid4(),
        status="completed",
        memories_written=3,
    )
    # No DB lookup, no send_message call, no raise — pure no-op.
    await service.handle_completion(event)


def _session_factory_returning(session: AsyncSession):
    """Return a callable that yields the given session via an async context manager."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _factory():
        yield session

    return _factory
