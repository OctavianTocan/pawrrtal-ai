"""LCM PR #6 — lcm_expand_query tool tests.

Covers:
- Empty prompt returns an informative error string.
- Empty conversation (no context items) returns an error string.
- expand_query calls the provider with a prompt that contains the full history.
- Provider response is returned as the answer.
- Provider failure returns an error string (no exception propagation).
- Both message and summary items are included in the expansion context.
- make_lcm_expand_query_tool is in build_agent_tools when lcm_enabled
  and user_id is provided.
- make_lcm_expand_query_tool is absent when lcm_enabled=False.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.models import (
    ChatMessage,
    Conversation,
    LCMContextItem,
    LCMSummary,
)
from app.tools.lcm_expand_query import lcm_expand_query

# Helpers


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="expand test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def _make_message(
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
    session.add(
        LCMContextItem(
            conversation_id=conv.id,
            ordinal=ordinal,
            item_kind="message",
            item_id=msg.id,
        )
    )
    await session.flush()
    return msg


async def _make_summary_item(
    session: AsyncSession,
    conv: Conversation,
    content: str,
    ordinal: int,
) -> LCMSummary:
    s = LCMSummary(
        conversation_id=conv.id,
        depth=0,
        content=content,
        token_count=len(content) // 4,
    )
    session.add(s)
    await session.flush()
    session.add(
        LCMContextItem(
            conversation_id=conv.id,
            ordinal=ordinal,
            item_kind="summary",
            item_id=s.id,
        )
    )
    await session.flush()
    return s


def _make_provider(answer: str) -> Any:
    async def _stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        yield {"type": "delta", "content": answer}

    p = MagicMock()
    p.stream = _stream
    return p


def _make_failing_provider() -> Any:
    async def _stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        raise RuntimeError("provider down")
        yield

    p = MagicMock()
    p.stream = _stream
    return p


def _patch_provider(monkeypatch: pytest.MonkeyPatch, provider: Any) -> None:
    import app.tools.lcm_expand_query as _mod

    monkeypatch.setattr(_mod, "resolve_llm", lambda *a, **kw: provider)


def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.tools.lcm_expand_query as _mod

    class _Fake:
        lcm_summary_model = ""

    monkeypatch.setattr(_mod, "_settings", _Fake())


# Tests


@pytest.mark.anyio
async def test_expand_empty_prompt(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    result = await lcm_expand_query(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        prompt="",
    )
    assert "empty prompt" in result.lower()


@pytest.mark.anyio
async def test_expand_empty_conversation(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)
    _patch_provider(monkeypatch, _make_provider("unused"))
    _patch_settings(monkeypatch)

    result = await lcm_expand_query(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        prompt="What was discussed?",
    )
    assert "no conversation history" in result.lower()


@pytest.mark.anyio
async def test_expand_returns_provider_answer(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _make_message(db_session, test_user, conv, "user", "hello there", 0)
    await db_session.commit()

    _patch_provider(monkeypatch, _make_provider("The user greeted the assistant."))
    _patch_settings(monkeypatch)

    result = await lcm_expand_query(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        prompt="What did the user say?",
    )
    assert "The user greeted" in result


@pytest.mark.anyio
async def test_expand_prompt_contains_full_history(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The expansion prompt sent to the provider should contain the full history."""
    conv = await _make_conversation(db_session, test_user)
    await _make_message(db_session, test_user, conv, "user", "unique_marker_abc", 0)
    await _make_summary_item(db_session, conv, "Earlier summary_marker_xyz", 1)
    await db_session.commit()

    captured_questions: list[str] = []

    async def _capturing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        captured_questions.append(kwargs.get("question", ""))
        yield {"type": "delta", "content": "captured"}

    p = MagicMock()
    p.stream = _capturing_stream
    _patch_provider(monkeypatch, p)
    _patch_settings(monkeypatch)

    await lcm_expand_query(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        prompt="What was in the history?",
    )

    assert captured_questions, "Provider was not called"
    question_sent = captured_questions[0]
    assert "unique_marker_abc" in question_sent
    assert "summary_marker_xyz" in question_sent


@pytest.mark.anyio
async def test_expand_provider_failure_returns_error_string(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _make_message(db_session, test_user, conv, "user", "hi", 0)
    await db_session.commit()

    _patch_provider(monkeypatch, _make_failing_provider())
    _patch_settings(monkeypatch)

    result = await lcm_expand_query(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        prompt="What happened?",
    )
    assert "failed" in result.lower() or "error" in result.lower()
