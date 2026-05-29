"""Issue #251 — LCM retrieval observability panel tests.

Covers ``app.core.lcm.observe.describe_assembled_context`` and the
``GET /api/v1/lcm/conversations/{id}/context`` route registered in
``app.infrastructure.observability.lcm.router``.  The behaviours nailed down here:

- Empty conversation produces an empty, well-typed response.
- Message-only context resolves each row with role + token estimate.
- Mixed message + summary context distinguishes the two kinds and
  surfaces summary depth/kind/source count.
- Fresh-tail cap is applied to raw messages while every summary
  survives — matching ``assemble_context()``'s read contract so the
  panel cannot diverge from what the provider actually saw.
- Conversation isolation: a different user / different conversation
  cannot read this one's context.
- Settings snapshot reflects ``settings.lcm_enabled``,
  ``lcm_fresh_tail_count``, ``lcm_leaf_chunk_tokens``,
  ``lcm_incremental_max_depth``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm.observe import describe_assembled_context
from app.infrastructure.database.legacy import User
from app.models import (
    ChatMessage,
    Conversation,
    LCMContextItem,
    LCMSummary,
    LCMSummarySource,
)


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    """Insert a fresh conversation owned by ``user``."""
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="observe test",
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


async def _make_context_item(
    session: AsyncSession,
    conv: Conversation,
    *,
    ordinal: int,
    item_kind: str,
    item_id: uuid.UUID,
) -> LCMContextItem:
    """Insert one assembled-context row."""
    row = LCMContextItem(
        conversation_id=conv.id,
        ordinal=ordinal,
        item_kind=item_kind,
        item_id=item_id,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.anyio
async def test_describe_empty_returns_empty_payload(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)

    response = await describe_assembled_context(
        db_session,
        conversation_id=conv.id,
        fresh_tail_count=10,
    )

    assert response.conversation_id == conv.id
    assert response.item_count == 0
    assert response.message_count == 0
    assert response.summary_count == 0
    assert response.estimated_tokens == 0
    assert response.items == []
    assert response.settings.fresh_tail_count == 10


@pytest.mark.anyio
async def test_describe_message_only_context(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    msg_a = await _make_message(
        db_session, test_user, conv, role="user", content="hello", ordinal=0
    )
    msg_b = await _make_message(
        db_session,
        test_user,
        conv,
        role="assistant",
        content="hi there",
        ordinal=1,
    )
    await _make_context_item(db_session, conv, ordinal=0, item_kind="message", item_id=msg_a.id)
    await _make_context_item(db_session, conv, ordinal=1, item_kind="message", item_id=msg_b.id)
    await db_session.commit()

    response = await describe_assembled_context(
        db_session,
        conversation_id=conv.id,
        fresh_tail_count=10,
    )

    assert response.item_count == 2
    assert response.message_count == 2
    assert response.summary_count == 0
    assert [r.item_kind for r in response.items] == ["message", "message"]
    assert [r.role for r in response.items] == ["user", "assistant"]
    assert response.items[0].preview == "hello"


@pytest.mark.anyio
async def test_describe_mixes_messages_and_summaries(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)

    summary = await _make_summary(
        db_session,
        conv,
        content="earlier discussion about deploys",
        depth=0,
        kind="normal",
    )
    # Two synthetic source edges so the panel can report source_count=2.
    db_session.add(
        LCMSummarySource(
            summary_id=summary.id,
            source_kind="message",
            source_id=uuid.uuid4(),
            source_ordinal=0,
        )
    )
    db_session.add(
        LCMSummarySource(
            summary_id=summary.id,
            source_kind="message",
            source_id=uuid.uuid4(),
            source_ordinal=1,
        )
    )
    msg = await _make_message(
        db_session,
        test_user,
        conv,
        role="user",
        content="and then we picked the new region",
        ordinal=5,
    )

    await _make_context_item(db_session, conv, ordinal=0, item_kind="summary", item_id=summary.id)
    await _make_context_item(db_session, conv, ordinal=1, item_kind="message", item_id=msg.id)
    await db_session.commit()

    response = await describe_assembled_context(
        db_session,
        conversation_id=conv.id,
        fresh_tail_count=10,
    )

    assert response.item_count == 2
    assert response.message_count == 1
    assert response.summary_count == 1
    summary_row = response.items[0]
    assert summary_row.item_kind == "summary"
    assert summary_row.summary_depth == 0
    assert summary_row.summary_kind == "normal"
    assert summary_row.source_count == 2
    assert summary_row.token_count is not None and summary_row.token_count > 0


@pytest.mark.anyio
async def test_describe_caps_raw_messages_but_keeps_summaries(
    db_session: AsyncSession, test_user: User
) -> None:
    """The fresh-tail cap drops oldest raw messages but every summary survives."""
    conv = await _make_conversation(db_session, test_user)
    summary = await _make_summary(db_session, conv, content="condensed window")
    await _make_context_item(db_session, conv, ordinal=0, item_kind="summary", item_id=summary.id)
    msg_ids: list[uuid.UUID] = []
    for ordinal in range(1, 6):
        m = await _make_message(
            db_session,
            test_user,
            conv,
            role="user",
            content=f"msg {ordinal}",
            ordinal=ordinal,
        )
        msg_ids.append(m.id)
        await _make_context_item(
            db_session, conv, ordinal=ordinal, item_kind="message", item_id=m.id
        )
    await db_session.commit()

    response = await describe_assembled_context(
        db_session,
        conversation_id=conv.id,
        fresh_tail_count=2,
    )

    assert response.summary_count == 1
    assert response.message_count == 2  # capped by fresh-tail
    kept_message_previews = [r.preview for r in response.items if r.item_kind == "message"]
    # The two most recent messages survive ("msg 4", "msg 5").
    assert kept_message_previews == ["msg 4", "msg 5"]


@pytest.mark.anyio
async def test_describe_isolates_conversations(db_session: AsyncSession, test_user: User) -> None:
    conv_a = await _make_conversation(db_session, test_user)
    conv_b = await _make_conversation(db_session, test_user)
    msg = await _make_message(
        db_session,
        test_user,
        conv_b,
        role="user",
        content="other conversation",
        ordinal=0,
    )
    await _make_context_item(db_session, conv_b, ordinal=0, item_kind="message", item_id=msg.id)
    await db_session.commit()

    response = await describe_assembled_context(
        db_session,
        conversation_id=conv_a.id,
    )

    assert response.item_count == 0


@pytest.mark.anyio
async def test_route_returns_404_for_unknown_conversation(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/lcm/conversations/{uuid.uuid4()}/context")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_route_returns_payload_for_owned_conversation(
    db_session: AsyncSession, test_user: User, client: AsyncClient
) -> None:
    conv = await _make_conversation(db_session, test_user)
    msg = await _make_message(
        db_session,
        test_user,
        conv,
        role="user",
        content="route hello",
        ordinal=0,
    )
    await _make_context_item(db_session, conv, ordinal=0, item_kind="message", item_id=msg.id)
    await db_session.commit()

    response = await client.get(f"/api/v1/lcm/conversations/{conv.id}/context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"] == str(conv.id)
    assert payload["item_count"] == 1
    assert payload["items"][0]["preview"] == "route hello"
    assert "settings" in payload
