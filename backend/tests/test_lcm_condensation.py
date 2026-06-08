"""Tests for incremental LCM condensation."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.lcm import assemble_context, compact_leaf_if_needed
from app.lcm.condense import _condense_at_depth
from app.models import (
    ChatMessage,
    Conversation,
    LCMContextItem,
    LCMSummary,
    LCMSummarySource,
)


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="condensation test",
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


async def _insert_summary_item(
    session: AsyncSession,
    conv: Conversation,
    content: str,
    ordinal: int,
    depth: int = 0,
) -> LCMSummary:
    """Insert a depth-d LCMSummary + its LCMContextItem at the given ordinal."""
    s = LCMSummary(
        conversation_id=conv.id,
        depth=depth,
        content=content,
        token_count=len(content) // 4,
        summary_kind="normal",
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


async def _seed_context(
    session: AsyncSession,
    user: User,
    conv: Conversation,
    turns: list[tuple[str, str]],
) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for i, (role, content) in enumerate(turns):
        msg = await _make_message(session, user, conv, role, content, i)
        session.add(
            LCMContextItem(conversation_id=conv.id, ordinal=i, item_kind="message", item_id=msg.id)
        )
        messages.append(msg)
    await session.commit()
    return messages


def _make_provider(answer: str = "CONDENSED") -> Any:
    async def _stream(*a: Any, **kw: Any) -> AsyncIterator[Any]:
        yield {"type": "delta", "content": answer}

    p = MagicMock()
    p.stream = _stream
    return p


def _patch(monkeypatch: pytest.MonkeyPatch, provider: Any) -> None:
    import app.lcm as _lcm
    import app.lcm.condense as _lcm_condense

    monkeypatch.setattr(_lcm, "_resolve_summary_provider", lambda *a, **kw: provider)
    monkeypatch.setattr(_lcm_condense, "_resolve_summary_provider", lambda *a, **kw: provider)


@pytest.mark.anyio
async def test_condense_noop_with_single_summary(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _insert_summary_item(db_session, conv, "just one summary", ordinal=0, depth=0)
    await db_session.commit()

    _patch(monkeypatch, _make_provider())
    ran = await _condense_at_depth(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        depth=0,
        max_chunk_tokens=100_000,
    )
    assert ran is False


@pytest.mark.anyio
async def test_condense_noop_no_summaries(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)
    _patch(monkeypatch, _make_provider())
    ran = await _condense_at_depth(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        depth=0,
        max_chunk_tokens=100_000,
    )
    assert ran is False


@pytest.mark.anyio
async def test_condense_creates_depth1_parent(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _insert_summary_item(db_session, conv, "leaf A", ordinal=0, depth=0)
    await _insert_summary_item(db_session, conv, "leaf B", ordinal=1, depth=0)
    await db_session.commit()

    _patch(monkeypatch, _make_provider("condensed AB"))
    ran = await _condense_at_depth(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        depth=0,
        max_chunk_tokens=100_000,
    )
    await db_session.commit()

    assert ran is True
    summaries = (
        (await db_session.execute(select(LCMSummary).where(LCMSummary.conversation_id == conv.id)))
        .scalars()
        .all()
    )
    depths = [s.depth for s in summaries]
    # Two depth-0 + one depth-1.
    assert depths.count(0) == 2
    assert depths.count(1) == 1
    parent = next(s for s in summaries if s.depth == 1)
    assert parent.content == "condensed AB"


@pytest.mark.anyio
async def test_condense_source_edges_point_at_leaves(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)
    leaf_a = await _insert_summary_item(db_session, conv, "leaf A", ordinal=0)
    leaf_b = await _insert_summary_item(db_session, conv, "leaf B", ordinal=1)
    await db_session.commit()

    _patch(monkeypatch, _make_provider("parent"))
    await _condense_at_depth(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        depth=0,
        max_chunk_tokens=100_000,
    )
    await db_session.commit()

    parent = (
        await db_session.execute(
            select(LCMSummary).where(
                LCMSummary.conversation_id == conv.id,
                LCMSummary.depth == 1,
            )
        )
    ).scalar_one()
    sources = (
        (
            await db_session.execute(
                select(LCMSummarySource).where(LCMSummarySource.summary_id == parent.id)
            )
        )
        .scalars()
        .all()
    )

    source_ids = {s.source_id for s in sources}
    assert leaf_a.id in source_ids
    assert leaf_b.id in source_ids
    for s in sources:
        assert s.source_kind == "summary"


@pytest.mark.anyio
async def test_condense_replaces_leaf_items_with_parent_item(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _insert_summary_item(db_session, conv, "leaf A", ordinal=0)
    await _insert_summary_item(db_session, conv, "leaf B", ordinal=1)
    # A raw message at ordinal 2 (shouldn't be touched).
    msg = await _make_message(db_session, test_user, conv, "user", "tail", 2)
    session = db_session
    session.add(
        LCMContextItem(conversation_id=conv.id, ordinal=2, item_kind="message", item_id=msg.id)
    )
    await db_session.commit()

    _patch(monkeypatch, _make_provider("parent"))
    await _condense_at_depth(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        depth=0,
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

    # 3 items before (2 leaf summaries + 1 message) →
    # 2 items after (1 depth-1 summary + 1 message).
    assert len(items) == 2
    assert items[0].item_kind == "summary"
    assert items[1].item_kind == "message"


@pytest.mark.anyio
async def test_compact_triggers_condensation_when_depth_ge_1(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)

    # Seed enough messages so two separate compactions each produce one leaf summary.
    for i in range(6):
        role = "user" if i % 2 == 0 else "assistant"
        msg = await _make_message(db_session, test_user, conv, role, f"msg{i}", i)
        db_session.add(
            LCMContextItem(conversation_id=conv.id, ordinal=i, item_kind="message", item_id=msg.id)
        )
    await db_session.commit()

    _patch(monkeypatch, _make_provider("compacted+condensed"))

    # Patch settings so incremental_max_depth=1 and fresh_tail=2.
    # Both ``app.lcm`` and ``app.lcm.condense`` hold their own
    # ``settings`` binding (each imported the symbol at module load),
    # so the patch has to land on both — otherwise the cascade reads
    # the real settings object and the test passes only by accident
    # when the real defaults happen to align with ``_S``.
    import app.lcm as _lcm
    import app.lcm.condense as _lcm_condense

    class _S:
        lcm_summary_model = ""
        lcm_fresh_tail_count = 2
        lcm_leaf_chunk_tokens = 100_000
        lcm_incremental_max_depth = 1

    fake_settings = _S()
    original_lcm = _lcm.settings
    original_condense = _lcm_condense.settings
    _lcm.settings = fake_settings  # type: ignore[assignment]
    _lcm_condense.settings = fake_settings  # type: ignore[assignment]
    try:
        # First compaction — compacts msgs 0-3 (4 items outside fresh tail of 2).
        await compact_leaf_if_needed(
            db_session,
            conversation_id=conv.id,
            user_id=test_user.id,
            model_id="gemini-2.5-flash",
            fresh_tail_count=2,
            max_chunk_tokens=100_000,
        )
        await db_session.commit()

        # Now the context has: [summary(depth=0)] + [msg4, msg5].
        # There's only one depth-0 summary, so condensation is a no-op.
        depth1_after_first = (
            (
                await db_session.execute(
                    select(LCMSummary).where(
                        LCMSummary.conversation_id == conv.id,
                        LCMSummary.depth == 1,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(depth1_after_first) == 0  # not enough leaves yet

        # Add two more messages so there's something outside the fresh tail again.
        for i in range(6, 8):
            role = "user" if i % 2 == 0 else "assistant"
            msg = await _make_message(db_session, test_user, conv, role, f"extra{i}", i)
            db_session.add(
                LCMContextItem(
                    conversation_id=conv.id,
                    ordinal=i,
                    item_kind="message",
                    item_id=msg.id,
                )
            )
        await db_session.commit()

        # Second compaction — the summary item (ordinal 0) is outside the fresh tail of 2.
        # But wait — the eligible window is items OUTSIDE the fresh tail.
        # We now have: [summary(0)][msg4(4-ish)][msg6(6)][msg7(7)].
        # Fresh tail = 2 → tail is msg6+msg7.
        # Eligible = summary(0) + msg4.
        # The summary item_kind is "summary" so it won't be leaf-compacted...
        # But msg4 is a message and IS eligible.
        # After compaction of msg4: [summary(0), new_leaf_summary(4), msg6, msg7].
        # Now there are 2 depth-0 summaries → condensation fires.
        await compact_leaf_if_needed(
            db_session,
            conversation_id=conv.id,
            user_id=test_user.id,
            model_id="gemini-2.5-flash",
            fresh_tail_count=2,
            max_chunk_tokens=100_000,
        )
        await db_session.commit()
    finally:
        _lcm.settings = original_lcm
        _lcm_condense.settings = original_condense

    # After the second compaction + condensation pass, there should be a depth-1 summary.
    all_summaries = (
        (await db_session.execute(select(LCMSummary).where(LCMSummary.conversation_id == conv.id)))
        .scalars()
        .all()
    )
    depths = [s.depth for s in all_summaries]
    assert 1 in depths, f"Expected a depth-1 summary, got depths: {depths}"


@pytest.mark.anyio
async def test_compact_skips_condensation_when_depth_is_0(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)

    # Pre-populate two depth-0 leaf summary context items.
    await _insert_summary_item(db_session, conv, "leaf A", ordinal=0, depth=0)
    await _insert_summary_item(db_session, conv, "leaf B", ordinal=1, depth=0)
    # Add fresh messages.
    for i in range(2, 4):
        msg = await _make_message(db_session, test_user, conv, "user", f"m{i}", i)
        db_session.add(
            LCMContextItem(conversation_id=conv.id, ordinal=i, item_kind="message", item_id=msg.id)
        )
    await db_session.commit()

    _patch(monkeypatch, _make_provider("leaf"))

    import app.lcm as _lcm
    import app.lcm.condense as _lcm_condense

    class _S:
        lcm_summary_model = ""
        lcm_fresh_tail_count = 2
        lcm_leaf_chunk_tokens = 100_000
        lcm_incremental_max_depth = 0  # <-- condensation disabled

    fake_settings = _S()
    original_lcm = _lcm.settings
    original_condense = _lcm_condense.settings
    _lcm.settings = fake_settings  # type: ignore[assignment]
    _lcm_condense.settings = fake_settings  # type: ignore[assignment]
    try:
        # compact_leaf_if_needed won't compact because the eligible items are
        # summaries (item_kind="summary"), not messages.  So it returns False
        # and no condensation runs.
        ran = await compact_leaf_if_needed(
            db_session,
            conversation_id=conv.id,
            user_id=test_user.id,
            model_id="gemini-2.5-flash",
            fresh_tail_count=2,
            max_chunk_tokens=100_000,
        )
        await db_session.commit()
    finally:
        _lcm.settings = original_lcm
        _lcm_condense.settings = original_condense

    # ran=False because compact_leaf sees no message items to compact;
    # condensation also did not run.
    assert ran is False
    depth1 = (
        (
            await db_session.execute(
                select(LCMSummary).where(
                    LCMSummary.conversation_id == conv.id,
                    LCMSummary.depth == 1,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(depth1) == 0


@pytest.mark.anyio
async def test_assemble_after_condensation(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await _make_conversation(db_session, test_user)
    await _insert_summary_item(db_session, conv, "leaf A", ordinal=0, depth=0)
    await _insert_summary_item(db_session, conv, "leaf B", ordinal=1, depth=0)
    msg = await _make_message(db_session, test_user, conv, "user", "fresh tail", 2)
    db_session.add(
        LCMContextItem(conversation_id=conv.id, ordinal=2, item_kind="message", item_id=msg.id)
    )
    await db_session.commit()

    _patch(monkeypatch, _make_provider("depth-1 condensed"))
    await _condense_at_depth(
        db_session,
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
        depth=0,
        max_chunk_tokens=100_000,
    )
    await db_session.commit()

    context = await assemble_context(db_session, conversation_id=conv.id, fresh_tail_count=64)

    assert len(context) == 2
    assert "[Summary of earlier conversation]" in context[0]["content"]
    assert "depth-1 condensed" in context[0]["content"]
    assert context[1] == {"role": "user", "content": "fresh tail"}
