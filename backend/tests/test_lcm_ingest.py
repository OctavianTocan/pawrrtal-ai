"""LCM PR #2 — ingest + assembly tests.

Covers:
- ``ingest_message`` creates an ``LCMContextItem`` with the correct ordinal
  and ``item_kind="message"``.
- Ordinals increment monotonically across consecutive ingests.
- ``assemble_context`` with fresh-tail-only returns rows in ascending ordinal
  order (oldest first), filtered to user/assistant roles.
- ``assemble_context`` respects ``fresh_tail_count`` — only the last N items
  are returned when the conversation is longer.
- ``assemble_context`` returns an empty list for a brand-new conversation.
- ``assemble_context`` silently skips ``item_kind="summary"`` rows (no
  summaries exist in PR #2, but the guard must not crash — PR #3 will add
  real coverage).
- A ``ChatMessage`` with a role other than user/assistant (e.g. ``system``)
  is filtered out.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm import assemble_context, ingest_message
from app.infrastructure.database.legacy import User
from app.models import (
    ChatMessage,
    Conversation,
    LCMContextItem,
    LCMSummary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="LCM ingest test",
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


# ---------------------------------------------------------------------------
# ingest_message
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ingest_creates_context_item(db_session: AsyncSession, test_user: User) -> None:
    """``ingest_message`` inserts exactly one LCMContextItem."""
    conv = await _make_conversation(db_session, test_user)
    msg = await _make_message(db_session, test_user, conv, "user", "hello", 0)

    item = await ingest_message(db_session, conversation_id=conv.id, message_id=msg.id)
    await db_session.commit()

    fetched = (
        await db_session.execute(select(LCMContextItem).where(LCMContextItem.id == item.id))
    ).scalar_one()

    assert fetched.item_kind == "message"
    assert fetched.item_id == msg.id
    assert fetched.conversation_id == conv.id
    assert fetched.ordinal == 0


@pytest.mark.anyio
async def test_ingest_ordinals_increment(db_session: AsyncSession, test_user: User) -> None:
    """Consecutive ingests get monotonically increasing ordinals."""
    conv = await _make_conversation(db_session, test_user)
    msgs = [
        await _make_message(db_session, test_user, conv, role, f"msg {i}", i)
        for i, role in enumerate(["user", "assistant", "user"])
    ]

    for msg in msgs:
        await ingest_message(db_session, conversation_id=conv.id, message_id=msg.id)
    await db_session.commit()

    result = await db_session.execute(
        select(LCMContextItem)
        .where(LCMContextItem.conversation_id == conv.id)
        .order_by(LCMContextItem.ordinal)
    )
    items = result.scalars().all()
    assert [item.ordinal for item in items] == [0, 1, 2]


@pytest.mark.anyio
async def test_ingest_ordinals_are_independent_per_conversation(
    db_session: AsyncSession, test_user: User
) -> None:
    """Each conversation has its own ordinal sequence starting at 0."""
    conv_a = await _make_conversation(db_session, test_user)
    conv_b = await _make_conversation(db_session, test_user)

    msg_a = await _make_message(db_session, test_user, conv_a, "user", "a0", 0)
    msg_b0 = await _make_message(db_session, test_user, conv_b, "user", "b0", 0)
    msg_b1 = await _make_message(db_session, test_user, conv_b, "assistant", "b1", 1)

    await ingest_message(db_session, conversation_id=conv_a.id, message_id=msg_a.id)
    await ingest_message(db_session, conversation_id=conv_b.id, message_id=msg_b0.id)
    await ingest_message(db_session, conversation_id=conv_b.id, message_id=msg_b1.id)
    await db_session.commit()

    result_a = await db_session.execute(
        select(LCMContextItem).where(LCMContextItem.conversation_id == conv_a.id)
    )
    result_b = await db_session.execute(
        select(LCMContextItem)
        .where(LCMContextItem.conversation_id == conv_b.id)
        .order_by(LCMContextItem.ordinal)
    )

    items_a = result_a.scalars().all()
    items_b = result_b.scalars().all()

    assert len(items_a) == 1
    assert items_a[0].ordinal == 0
    assert len(items_b) == 2
    assert [i.ordinal for i in items_b] == [0, 1]


# ---------------------------------------------------------------------------
# assemble_context
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_assemble_empty_conversation(db_session: AsyncSession, test_user: User) -> None:
    """An empty conversation returns an empty context list."""
    conv = await _make_conversation(db_session, test_user)
    result = await assemble_context(db_session, conversation_id=conv.id, fresh_tail_count=64)
    assert result == []


@pytest.mark.anyio
async def test_assemble_returns_oldest_first(db_session: AsyncSession, test_user: User) -> None:
    """assemble_context returns messages in ascending ordinal order."""
    conv = await _make_conversation(db_session, test_user)
    turns = [
        ("user", "hi"),
        ("assistant", "hello"),
        ("user", "how are you?"),
    ]
    for i, (role, text) in enumerate(turns):
        msg = await _make_message(db_session, test_user, conv, role, text, i)
        await ingest_message(db_session, conversation_id=conv.id, message_id=msg.id)
    await db_session.commit()

    context = await assemble_context(db_session, conversation_id=conv.id, fresh_tail_count=64)

    assert context == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "how are you?"},
    ]


@pytest.mark.anyio
async def test_assemble_respects_fresh_tail_count(
    db_session: AsyncSession, test_user: User
) -> None:
    """fresh_tail_count caps the returned window to the most recent N items."""
    conv = await _make_conversation(db_session, test_user)
    for i in range(5):
        role = "user" if i % 2 == 0 else "assistant"
        msg = await _make_message(db_session, test_user, conv, role, f"msg{i}", i)
        await ingest_message(db_session, conversation_id=conv.id, message_id=msg.id)
    await db_session.commit()

    context = await assemble_context(db_session, conversation_id=conv.id, fresh_tail_count=3)

    # Last 3 ordinals are 2, 3, 4 → contents "msg2", "msg3", "msg4".
    assert len(context) == 3
    assert context[0]["content"] == "msg2"
    assert context[-1]["content"] == "msg4"


@pytest.mark.anyio
async def test_assemble_keeps_summaries_when_messages_exceed_fresh_tail(
    db_session: AsyncSession, test_user: User
) -> None:
    """Regression: summaries at low ordinals must be delivered to the provider.

    After the first leaf compaction the context list looks like
    ``[summary@0, msg@1, ..., msg@N]`` with N > ``fresh_tail_count``.  A
    naive ``ORDER BY ordinal DESC LIMIT fresh_tail_count`` clips off the
    summary at ordinal 0, silently dropping the only handle the model has
    on the compacted history.  ``assemble_context`` must keep every
    summary while only capping the message tail.
    """
    conv = await _make_conversation(db_session, test_user)
    summary = LCMSummary(
        conversation_id=conv.id,
        depth=0,
        content="ancient history",
        token_count=5,
    )
    db_session.add(summary)
    await db_session.flush()
    db_session.add(
        LCMContextItem(
            conversation_id=conv.id,
            ordinal=0,
            item_kind="summary",
            item_id=summary.id,
        )
    )
    # 5 messages at ordinals 1-5; fresh_tail_count=3 → keep only msg2-4
    # (the last three messages) but ALSO keep the summary at ordinal 0.
    for i in range(5):
        msg = await _make_message(db_session, test_user, conv, "user", f"msg{i}", i)
        db_session.add(
            LCMContextItem(
                conversation_id=conv.id,
                ordinal=i + 1,
                item_kind="message",
                item_id=msg.id,
            )
        )
    await db_session.commit()

    context = await assemble_context(db_session, conversation_id=conv.id, fresh_tail_count=3)

    # First entry must be the summary (NOT clipped), followed by the
    # most-recent three messages.
    assert len(context) == 4
    assert context[0]["content"].startswith("[Summary of earlier conversation]")
    assert "ancient history" in context[0]["content"]
    assert [c["content"] for c in context[1:]] == ["msg2", "msg3", "msg4"]


@pytest.mark.anyio
async def test_assemble_filters_non_chat_roles(db_session: AsyncSession, test_user: User) -> None:
    """Messages with roles other than user/assistant are excluded."""
    conv = await _make_conversation(db_session, test_user)
    user_msg = await _make_message(db_session, test_user, conv, "user", "hi", 0)
    system_msg = await _make_message(db_session, test_user, conv, "system", "sys", 1)
    asst_msg = await _make_message(db_session, test_user, conv, "assistant", "hello", 2)
    for msg in (user_msg, system_msg, asst_msg):
        await ingest_message(db_session, conversation_id=conv.id, message_id=msg.id)
    await db_session.commit()

    context = await assemble_context(db_session, conversation_id=conv.id, fresh_tail_count=64)

    assert context == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


@pytest.mark.anyio
async def test_assemble_includes_summary_items(db_session: AsyncSession, test_user: User) -> None:
    """item_kind='summary' rows are resolved and returned as synthetic user messages.

    PR #3 added real summary support to assemble_context.  Summaries are
    injected as {"role": "user", "content": "[Summary of earlier conversation]\\n..."}.
    """
    conv = await _make_conversation(db_session, test_user)

    summary = LCMSummary(
        conversation_id=conv.id,
        depth=0,
        content="some older context",
        token_count=5,
    )
    db_session.add(summary)
    await db_session.flush()

    # Summary at ordinal 0, message at ordinal 1.
    db_session.add(
        LCMContextItem(
            conversation_id=conv.id,
            ordinal=0,
            item_kind="summary",
            item_id=summary.id,
        )
    )

    msg = await _make_message(db_session, test_user, conv, "user", "visible", 0)
    db_session.add(
        LCMContextItem(
            conversation_id=conv.id,
            ordinal=1,
            item_kind="message",
            item_id=msg.id,
        )
    )
    await db_session.commit()

    context = await assemble_context(db_session, conversation_id=conv.id, fresh_tail_count=64)

    # Summary comes first (ordinal 0), then the real message.
    assert len(context) == 2
    assert context[0]["role"] == "user"
    assert context[0]["content"].startswith("[Summary of earlier conversation]")
    assert "some older context" in context[0]["content"]
    assert context[1] == {"role": "user", "content": "visible"}
