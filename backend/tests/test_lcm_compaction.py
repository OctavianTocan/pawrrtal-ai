"""LCM leaf compaction tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.lcm import assemble_context, compact_leaf_if_needed
from app.models import LCMContextItem, LCMSummary, LCMSummarySource
from tests.lcm_helpers import (
    make_conversation as _make_conversation,
)
from tests.lcm_helpers import (
    make_failing_provider as _make_failing_provider,
)
from tests.lcm_helpers import (
    make_fake_provider as _make_fake_provider,
)
from tests.lcm_helpers import (
    patch_summary_provider as _patch_summary_provider,
)
from tests.lcm_helpers import (
    seed_context as _seed_context,
)


@pytest.mark.anyio
async def test_compact_noop_when_within_fresh_tail(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returns False when total items ≤ fresh_tail_count."""
    conv = await _make_conversation(db_session, test_user)
    await _seed_context(db_session, test_user, conv, [("user", "hi"), ("assistant", "hello")])

    provider = _make_fake_provider()
    _patch_summary_provider(monkeypatch, provider)

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
    _patch_summary_provider(monkeypatch, provider)

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
    _patch_summary_provider(monkeypatch, _make_fake_provider("compacted"))

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
    _patch_summary_provider(monkeypatch, _make_fake_provider("hello world summary"))

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
    _patch_summary_provider(monkeypatch, _make_fake_provider("summary text"))

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
    _patch_summary_provider(monkeypatch, _make_fake_provider("summary abc"))

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
    _patch_summary_provider(monkeypatch, _make_fake_provider("first only"))

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
    _patch_summary_provider(monkeypatch, _make_failing_provider())

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
    _patch_summary_provider(monkeypatch, _make_fake_provider("the summary"))

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
