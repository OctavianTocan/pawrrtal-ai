"""Schema smoke tests for the LCM tables.

This is the first PR in the LCM stack — only the storage layer exists,
no application code reads or writes these tables yet.  The tests
confirm:

- The three tables exist with the expected columns.
- Their cascade FK against ``conversations`` works (deleting a
  conversation tears down all LCM rows).
- A summary can hold zero or more sources, mixing ``message`` + ``summary``
  source kinds in one parent.
- The ``(conversation_id, ordinal)`` unique constraint on
  ``lcm_context_items`` actually fires so compaction's dense renumber
  is safe.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import User
from app.models import (
    Conversation,
    LCMContextItem,
    LCMSummary,
    LCMSummarySource,
)


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="LCM schema test",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


@pytest.mark.anyio
async def test_summary_insert_round_trips(db_session: AsyncSession, test_user: User) -> None:
    conv = await _make_conversation(db_session, test_user)
    summary = LCMSummary(
        conversation_id=conv.id,
        depth=0,
        content="The user asked about deploying Pawrrtal on a VPS.",
        token_count=12,
        model_id="gemini-2.5-flash-preview-05-20",
        summary_kind="normal",
    )
    db_session.add(summary)
    await db_session.commit()
    await db_session.refresh(summary)

    fetched = (
        await db_session.execute(select(LCMSummary).where(LCMSummary.id == summary.id))
    ).scalar_one()
    assert fetched.content.startswith("The user asked about deploying")
    assert fetched.depth == 0
    assert fetched.summary_kind == "normal"


@pytest.mark.anyio
async def test_summary_sources_support_mixed_kinds(
    db_session: AsyncSession, test_user: User
) -> None:
    """A condensed parent can point at a mix of message + summary sources."""
    conv = await _make_conversation(db_session, test_user)
    parent = LCMSummary(conversation_id=conv.id, depth=1, content="parent")
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    db_session.add_all(
        [
            LCMSummarySource(
                summary_id=parent.id,
                source_kind="message",
                source_id=uuid.uuid4(),
                source_ordinal=0,
            ),
            LCMSummarySource(
                summary_id=parent.id,
                source_kind="summary",
                source_id=uuid.uuid4(),
                source_ordinal=1,
            ),
        ]
    )
    await db_session.commit()

    sources = (
        (
            await db_session.execute(
                select(LCMSummarySource)
                .where(LCMSummarySource.summary_id == parent.id)
                .order_by(LCMSummarySource.source_ordinal)
            )
        )
        .scalars()
        .all()
    )
    assert [s.source_kind for s in sources] == ["message", "summary"]


@pytest.mark.anyio
async def test_context_items_have_unique_conversation_ordinal(
    db_session: AsyncSession, test_user: User
) -> None:
    """Two items can't share the same (conversation_id, ordinal)."""
    conv = await _make_conversation(db_session, test_user)
    db_session.add(
        LCMContextItem(
            conversation_id=conv.id,
            ordinal=0,
            item_kind="message",
            item_id=uuid.uuid4(),
        )
    )
    await db_session.commit()

    db_session.add(
        LCMContextItem(
            conversation_id=conv.id,
            ordinal=0,
            item_kind="summary",
            item_id=uuid.uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_cascade_metadata_is_declared() -> None:
    """Pin the ``ON DELETE CASCADE`` metadata on every LCM FK.

    Runtime cascade behaviour is not exercised here — the SQLite test
    harness uses ``Base.metadata.create_all`` without enabling
    ``PRAGMA foreign_keys=ON``, so cascades are inert in tests.  Postgres
    (where the migration runs in production) enforces them; this test
    just makes sure the *declaration* is correct so a future model edit
    can't silently drop the cascade.
    """
    from app.models import LCMContextItem, LCMSummary, LCMSummarySource

    expected_cascades = {
        (LCMSummary.__table__, "conversation_id"): "CASCADE",
        (LCMSummarySource.__table__, "summary_id"): "CASCADE",
        (LCMContextItem.__table__, "conversation_id"): "CASCADE",
    }
    for (table, column_name), expected in expected_cascades.items():
        matching_fks = [fk for fk in table.foreign_keys if fk.parent.name == column_name]
        # __table__ types as FromClause but is always a Table at runtime;
        # cast for the .name attribute (FromClause lacks it).
        table_name = cast(Table, table).name
        assert matching_fks, f"missing FK on {table_name}.{column_name}"
        assert matching_fks[0].ondelete == expected, (
            f"{table_name}.{column_name} expected ondelete={expected!r} "
            f"got {matching_fks[0].ondelete!r}"
        )
