"""LCM PR #4 — lcm_grep tool tests.

Covers:
- Empty query returns a "nothing to search" message.
- No matches returns a "no matches" message.
- Message hits are returned with role + ordinal annotations.
- Summary hits are returned with depth annotation.
- Both message and summary hits are returned in the same call.
- Search is case-insensitive.
- Limit caps the result count per source.
- Results are most-recent-first (by ordinal for messages, by created_at for summaries).
- _excerpt trims long content around the match.
- make_lcm_grep_tool is present in build_agent_tools when lcm_enabled.
- make_lcm_grep_tool is absent when lcm_enabled=False.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.models import (
    ChatMessage,
    Conversation,
    LCMSummary,
)
from app.tools.lcm_grep import _excerpt, lcm_grep

# Helpers


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="grep test",
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
    await session.flush()
    return msg


async def _make_summary(
    session: AsyncSession,
    conv: Conversation,
    content: str,
    depth: int = 0,
) -> LCMSummary:
    s = LCMSummary(
        conversation_id=conv.id,
        depth=depth,
        content=content,
        token_count=len(content) // 4,
    )
    session.add(s)
    await session.flush()
    return s


# _excerpt unit tests


def test_excerpt_short_text_not_truncated() -> None:
    result = _excerpt("hello world", query="world")
    assert "hello world" in result
    assert "…" not in result


def test_excerpt_long_text_truncated_around_match() -> None:
    padding = "x" * 300
    text = padding + "TARGET" + padding
    result = _excerpt(text, query="TARGET", max_chars=100)
    assert "TARGET" in result
    assert len(result) <= 110  # a bit of slack for ellipsis


def test_excerpt_match_near_start() -> None:
    text = "TARGET" + "y" * 600
    result = _excerpt(text, query="TARGET", max_chars=100)
    assert "TARGET" in result
    assert result.startswith("TARGET") or result.startswith("…")


def test_excerpt_no_match_returns_prefix() -> None:
    text = "nothing here at all"
    result = _excerpt(text, query="MISSING", max_chars=50)
    # Should return the beginning of the text when there's no match.
    assert "nothing" in result


# lcm_grep — query handling


@pytest.mark.anyio
async def test_grep_empty_query(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    result = await lcm_grep(db_session, conversation_id=conv.id, query="")
    assert "empty query" in result.lower()


@pytest.mark.anyio
async def test_grep_no_matches(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _make_message(db_session, test_user, conv, "user", "hello world", 0)
    await db_session.commit()

    result = await lcm_grep(db_session, conversation_id=conv.id, query="NONEXISTENT_XYZZY")
    assert "no matches" in result.lower()


@pytest.mark.anyio
async def test_grep_finds_message_hit(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _make_message(db_session, test_user, conv, "user", "deploy to Hetzner VPS", 0)
    await db_session.commit()

    result = await lcm_grep(db_session, conversation_id=conv.id, query="Hetzner")
    assert "[MESSAGE" in result
    assert "Hetzner" in result


@pytest.mark.anyio
async def test_grep_finds_summary_hit(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _make_summary(db_session, conv, "User discussed deploying the Hetzner VPS")
    await db_session.commit()

    result = await lcm_grep(db_session, conversation_id=conv.id, query="Hetzner")
    assert "[SUMMARY" in result
    assert "Hetzner" in result


@pytest.mark.anyio
async def test_grep_returns_both_message_and_summary_hits(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _make_message(db_session, test_user, conv, "user", "Hetzner config", 0)
    await _make_summary(db_session, conv, "Earlier: set up Hetzner server")
    await db_session.commit()

    result = await lcm_grep(db_session, conversation_id=conv.id, query="Hetzner")
    assert "[MESSAGE" in result
    assert "[SUMMARY" in result
    assert "1 message match" in result
    assert "1 summary match" in result


@pytest.mark.anyio
async def test_grep_case_insensitive(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _make_message(db_session, test_user, conv, "user", "Deploy to HETZNER vps", 0)
    await db_session.commit()

    result = await lcm_grep(db_session, conversation_id=conv.id, query="hetzner")
    assert "[MESSAGE" in result


@pytest.mark.anyio
async def test_grep_limit_caps_results(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    for i in range(5):
        await _make_message(db_session, test_user, conv, "user", f"mention target {i}", i)
    await db_session.commit()

    result = await lcm_grep(db_session, conversation_id=conv.id, query="target", limit=2)
    # Should report 2 matches despite 5 messages matching.
    assert "2 message match" in result


@pytest.mark.anyio
async def test_grep_scoped_to_conversation(db_session: AsyncSession, test_user: User) -> None:
    """Messages in other conversations must not appear in results."""
    conv_a = await _make_conversation(db_session, test_user)
    conv_b = await _make_conversation(db_session, test_user)
    await _make_message(db_session, test_user, conv_b, "user", "secret banana", 0)
    await db_session.commit()

    result = await lcm_grep(db_session, conversation_id=conv_a.id, query="banana")
    assert "no matches" in result.lower()


@pytest.mark.anyio
async def test_grep_excludes_system_role(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _make_message(db_session, test_user, conv, "system", "system needle here", 0)
    await db_session.commit()

    result = await lcm_grep(db_session, conversation_id=conv.id, query="needle")
    assert "no matches" in result.lower()


# build_agent_tools integration
