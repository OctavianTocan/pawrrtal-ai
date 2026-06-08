"""Shared helpers for LCM backend tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.models import ChatMessage, Conversation, LCMContextItem
from app.providers.base import StreamEvent


async def make_conversation(session: AsyncSession, user: User) -> Conversation:
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="LCM compaction test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def make_message(
    session: AsyncSession,
    user: User,
    conv: Conversation,
    role: str,
    content: str,
    ordinal: int,
) -> ChatMessage:
    msg = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        user_id=user.id,
        ordinal=ordinal,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(msg)
    await session.flush()
    return msg


async def seed_context(
    session: AsyncSession,
    user: User,
    conv: Conversation,
    turns: list[tuple[str, str]],
) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for index, (role, content) in enumerate(turns):
        msg = await make_message(session, user, conv, role, content, index)
        session.add(
            LCMContextItem(
                conversation_id=conv.id,
                ordinal=index,
                item_kind="message",
                item_id=msg.id,
            )
        )
        messages.append(msg)
    await session.commit()
    return messages


def make_fake_provider(summary_text: str = "SUMMARY") -> Any:
    async def _fake_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="delta", content=summary_text)

    provider = MagicMock()
    provider.stream = _fake_stream
    return provider


def make_failing_provider() -> Any:
    async def _failing_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[StreamEvent]:
        raise RuntimeError("LLM unavailable")
        yield

    provider = MagicMock()
    provider.stream = _failing_stream
    return provider


def patch_summary_provider(monkeypatch: pytest.MonkeyPatch, provider: Any) -> None:
    import app.lcm as lcm_module

    monkeypatch.setattr(lcm_module, "_resolve_summary_provider", lambda *_args, **_kwargs: provider)
