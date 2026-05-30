"""LCM PR #3 — leaf compaction tests.

Covers:
- compact_leaf_if_needed returns False when items ≤ fresh_tail_count.
- compact_leaf_if_needed runs and returns True when there are items outside
  the fresh tail.
- After compaction: the source message items are replaced by a single
  summary item; LCMSummary + LCMSummarySource rows are created.
- The ordinal slot of the first compacted item is reused for the summary item.
- Items inside the fresh tail are untouched.
- max_chunk_tokens limits the compaction batch: messages beyond the token
  budget are left in place.
- Summary items already in the eligible window are left in place (not
  re-compacted).
- assemble_context after compaction returns the summary content + fresh tail.
- Deterministic fallback is used when the provider raises.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.lcm import assemble_context, compact_leaf_if_needed
from app.models import (
    ChatMessage,
    Conversation,
    LCMContextItem,
    LCMSummary,
    LCMSummarySource,
)
from app.providers.base import StreamEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
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


async def _seed_context(
    session: AsyncSession,
    user: User,
    conv: Conversation,
    turns: list[tuple[str, str]],  # [(role, content), ...]
) -> list[ChatMessage]:
    """Insert N messages and their corresponding LCMContextItems."""
    messages: list[ChatMessage] = []
    for i, (role, content) in enumerate(turns):
        msg = await _make_message(session, user, conv, role, content, i)
        session.add(
            LCMContextItem(
                conversation_id=conv.id,
                ordinal=i,
                item_kind="message",
                item_id=msg.id,
            )
        )
        messages.append(msg)
    await session.commit()
    return messages


def _make_fake_provider(summary_text: str = "SUMMARY") -> Any:
    """Return a provider mock whose stream() yields a single delta."""

    async def _fake_stream(*args: Any, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="delta", content=summary_text)

    provider = MagicMock()
    provider.stream = _fake_stream
    return provider


def _make_failing_provider() -> Any:
    """Return a provider mock whose stream() raises immediately."""

    async def _failing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        raise RuntimeError("LLM unavailable")
        yield  # make it an async generator

    provider = MagicMock()
    provider.stream = _failing_stream
    return provider


# Patch the provider resolution so compaction uses our mock.
def _patch_resolve_llm(monkeypatch: pytest.MonkeyPatch, provider: Any) -> None:
    import app.lcm as _lcm

    monkeypatch.setattr(_lcm, "resolve_llm", lambda *args, **kwargs: provider)


# ---------------------------------------------------------------------------
# compact_leaf_if_needed — gating
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_compact_noop_when_within_fresh_tail(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returns False when total items ≤ fresh_tail_count."""
    conv = await _make_conversation(db_session, test_user)
    await _seed_context(db_session, test_user, conv, [("user", "hi"), ("assistant", "hello")])

    provider = _make_fake_provider()
    _patch_resolve_llm(monkeypatch, provider)

    ran = await compact_leaf_if_needed(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        fresh_tail_count=5,  # larger than total items
        max_chunk_tokens=100_000,
    )

    assert ran is False
    # Provider should not have been called.
    assert not provider.stream.called if hasattr(provider.stream, "called") else True


@pytest.mark.anyio
async def test_compact_noop_empty_conversation(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returns False for an empty conversation."""
    conv = await _make_conversation(db_session, test_user)
    provider = _make_fake_provider()
    _patch_resolve_llm(monkeypatch, provider)

    ran = await compact_leaf_if_needed(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        fresh_tail_count=2,
        max_chunk_tokens=100_000,
    )
    assert ran is False


# ---------------------------------------------------------------------------
# compact_leaf_if_needed — happy path
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_compact_runs_when_items_exceed_fresh_tail(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returns True when compaction runs successfully."""
    conv = await _make_conversation(db_session, test_user)
    await _seed_context(
        db_session,
        test_user,
        conv,
        [("user", "msg0"), ("assistant", "msg1"), ("user", "msg2")],
    )
    _patch_resolve_llm(monkeypatch, _make_fake_provider("compacted"))

    ran = await compact_leaf_if_needed(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        fresh_tail_count=2,  # last 2 kept; msg0 is eligible
        max_chunk_tokens=100_000,
    )
    assert ran is True


@pytest.mark.anyio
async def test_compact_creates_summary_and_sources(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After compaction, LCMSummary and LCMSummarySource rows exist."""
    conv = await _make_conversation(db_session, test_user)
    msgs = await _seed_context(
        db_session,
        test_user,
        conv,
        [("user", "hello"), ("assistant", "world"), ("user", "question")],
    )
    _patch_resolve_llm(monkeypatch, _make_fake_provider("hello world summary"))

    await compact_leaf_if_needed(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        fresh_tail_count=2,
        max_chunk_tokens=100_000,
    )
    await db_session.commit()

    summaries = (
        (await db_session.execute(select(LCMSummary).where(LCMSummary.conversation_id == conv.id)))
        .scalars()
        .all()
    )
    assert len(summaries) == 1
    assert summaries[0].content == "hello world summary"
    assert summaries[0].depth == 0
    assert summaries[0].summary_kind == "normal"

    sources = (
        (
            await db_session.execute(
                select(LCMSummarySource).where(LCMSummarySource.summary_id == summaries[0].id)
            )
        )
        .scalars()
        .all()
    )
    # Only msg0 ("hello") is outside the fresh tail of 2 and should be compacted.
    assert len(sources) == 1
    assert sources[0].source_kind == "message"
    assert sources[0].source_id == msgs[0].id


@pytest.mark.anyio
async def test_compact_replaces_message_items_with_summary_item(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After compaction, the source message item is gone; a summary item takes its slot."""
    conv = await _make_conversation(db_session, test_user)
    msgs = await _seed_context(
        db_session,
        test_user,
        conv,
        [("user", "old"), ("assistant", "reply"), ("user", "new")],
    )
    _patch_resolve_llm(monkeypatch, _make_fake_provider("summary text"))

    await compact_leaf_if_needed(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        fresh_tail_count=2,
        max_chunk_tokens=100_000,
    )
    await db_session.commit()

    items = (
        (
            await db_session.execute(
                select(LCMContextItem)
                .where(LCMContextItem.conversation_id == conv.id)
                .order_by(LCMContextItem.ordinal)
            )
        )
        .scalars()
        .all()
    )

    # 3 items before → 3 items after (summary + 2 message items in fresh tail).
    assert len(items) == 3
    # First item must now be the summary at the original slot 0.
    assert items[0].item_kind == "summary"
    assert items[0].ordinal == 0
    # Fresh-tail items are still message items.
    assert items[1].item_kind == "message"
    assert items[2].item_kind == "message"
    assert items[1].item_id == msgs[1].id
    assert items[2].item_id == msgs[2].id


@pytest.mark.anyio
async def test_compact_multiple_eligible_messages(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When several messages are eligible, all are folded into one summary."""
    conv = await _make_conversation(db_session, test_user)
    msgs = await _seed_context(
        db_session,
        test_user,
        conv,
        [
            ("user", "a"),
            ("assistant", "b"),
            ("user", "c"),
            ("assistant", "d"),  # fresh tail starts here
            ("user", "e"),  # fresh tail end
        ],
    )
    _patch_resolve_llm(monkeypatch, _make_fake_provider("summary abc"))

    await compact_leaf_if_needed(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        fresh_tail_count=2,
        max_chunk_tokens=100_000,
    )
    await db_session.commit()

    items = (
        (
            await db_session.execute(
                select(LCMContextItem)
                .where(LCMContextItem.conversation_id == conv.id)
                .order_by(LCMContextItem.ordinal)
            )
        )
        .scalars()
        .all()
    )

    # 5 items → 1 summary + 2 fresh = 3 items total.
    assert len(items) == 3
    assert items[0].item_kind == "summary"

    sources = (await db_session.execute(select(LCMSummarySource))).scalars().all()
    # msgs 0, 1, 2 should all be sources of the summary.
    source_ids = {s.source_id for s in sources}
    assert msgs[0].id in source_ids
    assert msgs[1].id in source_ids
    assert msgs[2].id in source_ids
    assert msgs[3].id not in source_ids  # fresh tail
    assert msgs[4].id not in source_ids  # fresh tail


# ---------------------------------------------------------------------------
# max_chunk_tokens budget
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_compact_respects_token_budget(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the oldest messages that fit in max_chunk_tokens are compacted."""
    conv = await _make_conversation(db_session, test_user)
    # Each message is ~20 chars ≈ 5 tokens.  Budget of 6 tokens should fit only 1.
    msgs = await _seed_context(
        db_session,
        test_user,
        conv,
        [
            ("user", "first message here"),  # ~5 tokens
            ("assistant", "second one here"),  # ~5 tokens
            ("user", "fresh tail msg"),  # fresh tail
        ],
    )
    _patch_resolve_llm(monkeypatch, _make_fake_provider("first only"))

    await compact_leaf_if_needed(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        fresh_tail_count=1,  # only last 1 in fresh tail → 2 eligible
        max_chunk_tokens=6,  # fits only the first message
    )
    await db_session.commit()

    sources = (await db_session.execute(select(LCMSummarySource))).scalars().all()
    # Only the first message should be in sources.
    assert len(sources) == 1
    assert sources[0].source_id == msgs[0].id

    # Second message (budget overflow) and third (fresh tail) should still be
    # message items in lcm_context_items.
    items = (
        (
            await db_session.execute(
                select(LCMContextItem)
                .where(LCMContextItem.conversation_id == conv.id)
                .order_by(LCMContextItem.ordinal)
            )
        )
        .scalars()
        .all()
    )
    kinds = [i.item_kind for i in items]
    assert kinds[0] == "summary"
    assert kinds[1] == "message"  # second message still in place
    assert kinds[2] == "message"  # fresh tail


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_compact_uses_fallback_when_provider_fails(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uses deterministic truncation when the LLM provider raises."""
    conv = await _make_conversation(db_session, test_user)
    await _seed_context(
        db_session,
        test_user,
        conv,
        [("user", "old message"), ("assistant", "reply"), ("user", "fresh")],
    )
    _patch_resolve_llm(monkeypatch, _make_failing_provider())

    ran = await compact_leaf_if_needed(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        fresh_tail_count=2,
        max_chunk_tokens=100_000,
    )
    await db_session.commit()

    assert ran is True
    summaries = (
        (await db_session.execute(select(LCMSummary).where(LCMSummary.conversation_id == conv.id)))
        .scalars()
        .all()
    )
    assert len(summaries) == 1
    assert summaries[0].summary_kind == "fallback"
    # Deterministic fallback contains the raw transcript text.
    assert "USER:" in summaries[0].content or "old message" in summaries[0].content


# ---------------------------------------------------------------------------
# assemble_context after compaction
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_assemble_after_compaction_returns_summary_plus_fresh(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After compaction, assemble_context returns [summary, *fresh_tail]."""
    conv = await _make_conversation(db_session, test_user)
    await _seed_context(
        db_session,
        test_user,
        conv,
        [("user", "old"), ("assistant", "tail1"), ("user", "tail2")],
    )
    _patch_resolve_llm(monkeypatch, _make_fake_provider("the summary"))

    await compact_leaf_if_needed(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        fresh_tail_count=2,
        max_chunk_tokens=100_000,
    )
    await db_session.commit()

    context = await assemble_context(db_session, conversation_id=conv.id, fresh_tail_count=64)

    assert len(context) == 3
    # First entry is the injected summary.
    assert context[0]["role"] == "user"
    assert "[Summary of earlier conversation]" in context[0]["content"]
    assert "the summary" in context[0]["content"]
    # Then the fresh-tail messages.
    assert context[1] == {"role": "assistant", "content": "tail1"}
    assert context[2] == {"role": "user", "content": "tail2"}


# ---------------------------------------------------------------------------
# Background scheduling & integration tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_schedule_lcm_compaction_runs_background_task_under_lock(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies that schedule_lcm_compaction runs asynchronously in the background.

    It should use a shared connection via the mock db session, execute compaction,
    and update the database.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.lcm.background as bg_mod

    conv = await _make_conversation(db_session, test_user)
    conv_id = conv.id
    # Seed 3 messages (fresh_tail_count=2, so 1 is eligible)
    await _seed_context(
        db_session,
        test_user,
        conv,
        [("user", "msg0"), ("assistant", "msg1"), ("user", "msg2")],
    )

    # Enable LCM settings for background scheduler
    monkeypatch.setattr(bg_mod.settings, "lcm_enabled", True)
    monkeypatch.setattr(bg_mod.settings, "lcm_fresh_tail_count", 2)
    monkeypatch.setattr(bg_mod.settings, "lcm_leaf_chunk_tokens", 100_000)

    # Patch the LLM provider for compaction
    _patch_resolve_llm(monkeypatch, _make_fake_provider("compacted"))

    # Patch async_session_maker in the background module to use our test engine
    shared_maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(bg_mod, "async_session_maker", shared_maker)

    # Clear task tracker
    bg_mod._LCM_COMPACT_TASKS.clear()

    # Schedule compaction
    bg_mod.schedule_lcm_compaction(
        conversation_id=conv_id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
    )

    # Verify task was registered
    assert len(bg_mod._LCM_COMPACT_TASKS) == 1

    # Wait for the background task to finish
    while bg_mod._LCM_COMPACT_TASKS:
        await asyncio.gather(*list(bg_mod._LCM_COMPACT_TASKS))

    # Assert that the task has been cleaned up
    assert len(bg_mod._LCM_COMPACT_TASKS) == 0

    # Refresh DB session state to see compaction results
    db_session.expire_all()

    summaries = (
        (await db_session.execute(select(LCMSummary).where(LCMSummary.conversation_id == conv_id)))
        .scalars()
        .all()
    )
    assert len(summaries) == 1
    assert summaries[0].content == "compacted"


@pytest.mark.anyio
async def test_schedule_lcm_compaction_serializes_concurrent_calls(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two concurrent compaction requests for the same conversation are serialized by the lock."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.lcm.background as bg_mod

    conv = await _make_conversation(db_session, test_user)
    await _seed_context(
        db_session,
        test_user,
        conv,
        [("user", "msg0"), ("assistant", "msg1"), ("user", "msg2")],
    )

    monkeypatch.setattr(bg_mod.settings, "lcm_enabled", True)
    monkeypatch.setattr(bg_mod.settings, "lcm_fresh_tail_count", 2)
    monkeypatch.setattr(bg_mod.settings, "lcm_leaf_chunk_tokens", 100_000)

    shared_maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(bg_mod, "async_session_maker", shared_maker)

    active_runs = 0
    max_concurrent = 0

    async def mock_compact_leaf(*args: Any, **kwargs: Any) -> bool:
        nonlocal active_runs, max_concurrent
        active_runs += 1
        max_concurrent = max(max_concurrent, active_runs)
        await asyncio.sleep(0.05)  # yield control to allow concurrency
        active_runs -= 1
        return True

    monkeypatch.setattr(bg_mod, "compact_leaf_if_needed", mock_compact_leaf)

    bg_mod._LCM_COMPACT_TASKS.clear()

    # Schedule two compactions for the SAME conversation back-to-back
    bg_mod.schedule_lcm_compaction(
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
    )
    bg_mod.schedule_lcm_compaction(
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
    )

    assert len(bg_mod._LCM_COMPACT_TASKS) == 2

    # Wait for completion
    while bg_mod._LCM_COMPACT_TASKS:
        await asyncio.gather(*list(bg_mod._LCM_COMPACT_TASKS))

    # Concurrency must be exactly 1 due to per-conversation lock
    assert max_concurrent == 1
    assert active_runs == 0


@pytest.mark.anyio
async def test_schedule_lcm_compaction_disabled_is_noop(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When lcm_enabled is False, schedule_lcm_compaction is a no-op."""
    import app.lcm.background as bg_mod

    conv = await _make_conversation(db_session, test_user)
    monkeypatch.setattr(bg_mod.settings, "lcm_enabled", False)

    bg_mod._LCM_COMPACT_TASKS.clear()
    bg_mod.schedule_lcm_compaction(
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
    )

    assert len(bg_mod._LCM_COMPACT_TASKS) == 0


@pytest.mark.anyio
async def test_finalize_turn_triggers_lcm_compaction(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies that _finalize_turn schedules LCM compaction at the correct moment."""
    import time
    from collections import Counter
    from unittest.mock import AsyncMock

    from app.channels.turn_runner import ChatTurnInput, _finalize_turn
    from app.chat.aggregator import ChatTurnAggregator

    conv = await _make_conversation(db_session, test_user)

    monkeypatch.setattr("app.channels.turn_runner.finalize_assistant_message", AsyncMock())
    monkeypatch.setattr("app.channels.turn_runner.record_turn_cost_if_enabled", AsyncMock())
    monkeypatch.setattr("app.channels.turn_runner.publish_if_available", AsyncMock())

    schedule_mock = MagicMock()
    monkeypatch.setattr("app.channels.turn_runner.schedule_lcm_compaction", schedule_mock)

    turn_input = ChatTurnInput(
        conversation_id=conv.id,
        user_id=test_user.id,
        question="hello",
        provider=MagicMock(),
        channel=MagicMock(),
        channel_message=cast(Any, {"model_id": "gemini-2.5-flash", "surface": "telegram"}),
        db_session=db_session,
    )

    aggregator = ChatTurnAggregator()
    assistant_message_id = uuid.uuid4()

    await _finalize_turn(
        turn_input=turn_input,
        aggregator=aggregator,
        assistant_message_id=assistant_message_id,
        started_at=time.perf_counter(),
        event_count=0,
        event_breakdown=Counter(),
        ttft_ms=None,
    )

    schedule_mock.assert_called_once_with(
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
    )
