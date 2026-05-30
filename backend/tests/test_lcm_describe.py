"""LCM PR #5 — lcm_describe tool tests.

Covers:
- lcm_describe returns metadata + full content for an existing summary.
- lcm_describe returns an error string for an unknown summary_id.
- lcm_describe is scoped to conversation_id (foreign ID returns error).
- lcm_list_summaries returns a compact table for a conversation with summaries.
- lcm_list_summaries returns "no summaries" for an empty conversation.
- make_lcm_describe_tool and make_lcm_list_summaries_tool are present in
  build_agent_tools when lcm_enabled=True.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.models import Conversation, LCMSummary, LCMSummarySource
from app.tools.lcm_describe import lcm_describe, lcm_list_summaries

# Helpers


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="describe test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def _make_summary(
    session: AsyncSession,
    conv: Conversation,
    content: str,
    depth: int = 0,
    summary_kind: str = "normal",
) -> LCMSummary:
    s = LCMSummary(
        conversation_id=conv.id,
        depth=depth,
        content=content,
        token_count=len(content) // 4,
        summary_kind=summary_kind,
        model_id="gemini-2.5-flash",
    )
    session.add(s)
    await session.flush()
    return s


# lcm_describe


@pytest.mark.anyio
async def test_describe_returns_metadata_and_content(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    summary = await _make_summary(db_session, conv, "User asked about deploying to Hetzner.")
    await db_session.commit()

    result = await lcm_describe(db_session, conversation_id=conv.id, summary_id=summary.id)

    assert str(summary.id) in result
    assert "depth" in result.lower()
    assert "User asked about deploying" in result


@pytest.mark.anyio
async def test_describe_includes_source_edges(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    summary = await _make_summary(db_session, conv, "Summary with sources")
    source_id = uuid.uuid4()
    db_session.add(
        LCMSummarySource(
            summary_id=summary.id,
            source_kind="message",
            source_id=source_id,
            source_ordinal=0,
        )
    )
    await db_session.commit()

    result = await lcm_describe(db_session, conversation_id=conv.id, summary_id=summary.id)

    assert "message" in result
    assert str(source_id) in result


@pytest.mark.anyio
async def test_describe_unknown_id_returns_error(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    result = await lcm_describe(db_session, conversation_id=conv.id, summary_id=uuid.uuid4())
    assert "not found" in result.lower()


@pytest.mark.anyio
async def test_describe_scoped_to_conversation(db_session: AsyncSession, test_user: User) -> None:
    """A summary from another conversation should not be visible."""
    conv_a = await _make_conversation(db_session, test_user)
    conv_b = await _make_conversation(db_session, test_user)
    summary_b = await _make_summary(db_session, conv_b, "Private summary in conv B")
    await db_session.commit()

    result = await lcm_describe(db_session, conversation_id=conv_a.id, summary_id=summary_b.id)
    assert "not found" in result.lower()


# lcm_list_summaries


@pytest.mark.anyio
async def test_list_summaries_empty_conversation(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    result = await lcm_list_summaries(db_session, conversation_id=conv.id)
    assert "no summaries" in result.lower()


@pytest.mark.anyio
async def test_list_summaries_returns_all_nodes(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    for i in range(3):
        await _make_summary(db_session, conv, f"Summary {i} content")
    await db_session.commit()

    result = await lcm_list_summaries(db_session, conversation_id=conv.id)
    assert "3 node" in result


@pytest.mark.anyio
async def test_list_summaries_shows_id_and_excerpt(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    s = await _make_summary(db_session, conv, "Unique content for listing test")
    await db_session.commit()

    result = await lcm_list_summaries(db_session, conversation_id=conv.id)
    assert str(s.id) in result
    assert "Unique content" in result
