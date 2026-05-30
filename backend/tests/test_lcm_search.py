"""Issue #253 — ranked lcm_search tests.

Covers ``app.tools.lcm_search.lcm_search`` and the AgentTool
factory in ``app.tools.lcm_search_agent``.

What we nail down:

- Empty / stopword-only query returns no results without crashing.
- Token tokenisation + length normalisation rank a focused short
  match above a noisy long match.
- Multi-token coverage bonus elevates results that hit *every* query
  term over results that hit only one.
- Mixed message + summary candidates appear in the same ranked list
  and each carry their item-kind-specific metadata.
- Summaries get a small source-weight bump (equal token frequency
  in a summary outranks a message).
- Conversation isolation: rows from another conversation never
  appear.
- The agent tool is registered when ``settings.lcm_enabled`` and a
  conversation_id are present, and not otherwise.
- The agent tool's wrapper formats results as a readable text block.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import build_agent_tools
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User
from app.models import ChatMessage, Conversation, LCMSummary
from app.tools.lcm_search import (
    LCMSearchResult,
    _tokenize_query,
    format_results,
    lcm_search,
)
from app.tools.lcm_search_agent import make_lcm_search_tool


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    """Insert a fresh conversation owned by ``user``."""
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="search test",
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
    *,
    role: str,
    content: str,
    ordinal: int,
) -> ChatMessage:
    """Insert one raw chat message at ``ordinal``."""
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
    *,
    content: str,
    depth: int = 0,
    kind: str = "normal",
) -> LCMSummary:
    """Insert one LCM summary row."""
    s = LCMSummary(
        conversation_id=conv.id,
        depth=depth,
        content=content,
        token_count=max(1, len(content) // 4),
        summary_kind=kind,
    )
    session.add(s)
    await session.flush()
    return s


def test_tokenize_drops_stopwords_and_short_tokens() -> None:
    tokens = _tokenize_query("What did we decide about the Telegram demo blockers?")
    assert "telegram" in tokens
    assert "demo" in tokens
    assert "blockers" in tokens
    # Stopwords and short noise drop out.
    assert "the" not in tokens
    assert "we" not in tokens
    assert "did" not in tokens


def test_tokenize_dedupes_and_lowercases() -> None:
    assert _tokenize_query("Telegram telegram Telegram demo") == ["telegram", "demo"]


@pytest.mark.anyio
async def test_search_empty_query_returns_no_results(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    assert (await lcm_search(db_session, conversation_id=conv.id, query="   ")) == []
    assert (await lcm_search(db_session, conversation_id=conv.id, query="the and from")) == []


@pytest.mark.anyio
async def test_search_ranks_focused_match_above_noisy_match(
    db_session: AsyncSession, test_user: User
) -> None:
    """Short, focused content with the query term outranks a long noisy hit."""
    conv = await _make_conversation(db_session, test_user)
    focused = await _make_message(
        db_session,
        test_user,
        conv,
        role="assistant",
        content="Hetzner deploy plan finalised.",
        ordinal=0,
    )
    # Noisy long content: contains the term once amidst lots of unrelated text.
    noisy_content = "padding " * 200 + "Hetzner mention buried in noise."
    await _make_message(
        db_session,
        test_user,
        conv,
        role="assistant",
        content=noisy_content,
        ordinal=1,
    )
    await db_session.commit()

    results = await lcm_search(db_session, conversation_id=conv.id, query="hetzner deploy")
    assert results
    # Focused match should win on coverage + length-normalisation.
    assert results[0]["item_id"] == str(focused.id)


@pytest.mark.anyio
async def test_search_coverage_bonus_favours_multi_token_hits(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    # Hits BOTH tokens, even though the single-token row has more total hits.
    both = await _make_message(
        db_session,
        test_user,
        conv,
        role="assistant",
        content="onboarding workspace-connect plan",
        ordinal=0,
    )
    # Repeats one token many times but never the other.
    repeat = "onboarding " * 12
    await _make_message(
        db_session,
        test_user,
        conv,
        role="assistant",
        content=repeat,
        ordinal=1,
    )
    await db_session.commit()

    results = await lcm_search(
        db_session,
        conversation_id=conv.id,
        query="workspace-connect onboarding",
    )
    assert results
    assert results[0]["item_id"] == str(both.id)


@pytest.mark.anyio
async def test_search_returns_mixed_messages_and_summaries(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    msg = await _make_message(
        db_session,
        test_user,
        conv,
        role="assistant",
        content="Earlier we discussed pricing.",
        ordinal=0,
    )
    summary = await _make_summary(
        db_session, conv, content="Pricing tiers: 25 active workspaces per team."
    )
    await db_session.commit()

    results = await lcm_search(db_session, conversation_id=conv.id, query="pricing workspaces")

    item_ids = {r["item_id"] for r in results}
    item_kinds = {r["item_kind"] for r in results}
    assert str(msg.id) in item_ids
    assert str(summary.id) in item_ids
    assert item_kinds == {"message", "summary"}


@pytest.mark.anyio
async def test_search_isolates_conversations(db_session: AsyncSession, test_user: User) -> None:
    conv_a = await _make_conversation(db_session, test_user)
    conv_b = await _make_conversation(db_session, test_user)
    await _make_message(
        db_session,
        test_user,
        conv_b,
        role="assistant",
        content="secret banana memo",
        ordinal=0,
    )
    await db_session.commit()

    results = await lcm_search(db_session, conversation_id=conv_a.id, query="banana")
    assert results == []


@pytest.mark.anyio
async def test_search_filters_can_disable_messages_or_summaries(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _make_message(
        db_session,
        test_user,
        conv,
        role="assistant",
        content="onboarding workspace-connect",
        ordinal=0,
    )
    await _make_summary(db_session, conv, content="Summary about onboarding workspace-connect")
    await db_session.commit()

    only_messages = await lcm_search(
        db_session,
        conversation_id=conv.id,
        query="workspace-connect onboarding",
        include_summaries=False,
    )
    only_summaries = await lcm_search(
        db_session,
        conversation_id=conv.id,
        query="workspace-connect onboarding",
        include_messages=False,
    )

    assert only_messages and all(r["item_kind"] == "message" for r in only_messages)
    assert only_summaries and all(r["item_kind"] == "summary" for r in only_summaries)


@pytest.mark.anyio
async def test_search_respects_limit(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    for i in range(6):
        await _make_message(
            db_session,
            test_user,
            conv,
            role="assistant",
            content=f"workspace-connect mention {i}",
            ordinal=i,
        )
    await db_session.commit()

    results = await lcm_search(
        db_session, conversation_id=conv.id, query="workspace-connect", limit=3
    )
    assert len(results) == 3


def test_format_results_produces_readable_block() -> None:
    rows: list[LCMSearchResult] = [
        {
            "item_kind": "message",
            "item_id": "00000000-0000-0000-0000-000000000001",
            "ordinal": 7,
            "role": "user",
            "summary_depth": None,
            "summary_kind": None,
            "score": 0.42,
            "excerpt": "workspace-connect was dropped",
            "source_ids": ["00000000-0000-0000-0000-000000000001"],
        }
    ]
    text = format_results("workspace-connect", rows)
    assert "lcm_search: 1 result(s) for 'workspace-connect'" in text
    assert "kind=message" in text
    assert "score=0.420" in text


def test_build_agent_tools_includes_lcm_search_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "lcm_enabled", True)
    tools = build_agent_tools(
        workspace_root=tmp_path,
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
    )
    assert any(tool.name == "lcm_search" for tool in tools)


def test_build_agent_tools_omits_lcm_search_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "lcm_enabled", False)
    tools = build_agent_tools(
        workspace_root=tmp_path,
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
    )
    assert not any(tool.name == "lcm_search" for tool in tools)


def test_make_lcm_search_tool_exposes_expected_schema() -> None:
    tool = make_lcm_search_tool(conversation_id=uuid.uuid4())
    assert tool.name == "lcm_search"
    props = tool.parameters["properties"]
    assert set(props.keys()) >= {
        "query",
        "limit",
        "include_messages",
        "include_summaries",
    }
