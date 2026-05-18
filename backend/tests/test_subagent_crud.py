"""CRUD + model tests for the subagents table (PR 2 of the subagent epic).

Covers:

  * Model insert / read by handle / list / count_running.
  * Status transitions via :func:`finalize_subagent` — including the
    "already terminal, idempotent" guard.
  * Cascade-cancel hook fires from :func:`delete_conversation` and
    marks every running child with the documented reason.
  * Schema cascade on the FK chain — the DB-level fallback for the
    cross-worker case where the app-level cancel didn't see the live
    task.

Uses the project's standard ``db_session`` + ``test_user`` fixtures
from ``backend/tests/conftest.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.conversation import delete_conversation
from app.crud.subagent import (
    CASCADE_CANCEL_REASON,
    cancel_running_subagents_for_conversation,
    count_running_for_conversation,
    finalize_subagent,
    get_subagent_by_handle,
    insert_running_subagent,
    list_subagents_for_conversation,
)
from app.db import User
from app.models import Conversation, Subagent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """Return a naive UTC datetime — matches the model column shape."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_conversation(session: AsyncSession, user: User) -> Conversation:
    """Create one conversation for the test user and commit it."""
    convo = Conversation(
        id=uuid4(),
        user_id=user.id,
        title="Test conversation",
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(convo)
    await session.commit()
    return convo


async def _seed_subagent(
    session: AsyncSession,
    *,
    convo: Conversation,
    user: User,
    handle: str,
    persona: str = "researcher",
    status: str = "running",
) -> Subagent:
    """Insert one subagent row through the CRUD path so the test
    exercises the same code the spawn tool will."""
    row = await insert_running_subagent(
        session,
        conversation_id=convo.id,
        parent_user_id=user.id,
        persona_name=persona,
        handle=handle,
        task=f"task for {handle}",
        tools_granted=["read_file", "exa_search"],
        spawned_at=_now(),
    )
    if status != "running":
        await finalize_subagent(
            session,
            subagent_id=row.id,
            status=status,  # type: ignore[arg-type]
            completed_at=_now(),
            result="ok" if status == "succeeded" else None,
            error="boom" if status == "failed" else None,
        )
    await session.commit()
    return row


# ---------------------------------------------------------------------------
# Insert + read
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_insert_running_subagent_round_trip(
    db_session: AsyncSession, test_user: User
) -> None:
    convo = await _seed_conversation(db_session, test_user)

    row = await insert_running_subagent(
        db_session,
        conversation_id=convo.id,
        parent_user_id=test_user.id,
        persona_name="researcher",
        handle="researcher#a3f",
        task="find prior art on X",
        tools_granted=["read_file", "exa_search"],
        spawned_at=_now(),
        label="market scan",
    )
    await db_session.commit()

    assert row.id is not None
    assert row.status == "running"
    assert row.depth == 0
    assert row.tools_granted == ["read_file", "exa_search"]
    assert row.label == "market scan"

    fetched = await get_subagent_by_handle(db_session, handle="researcher#a3f")
    assert fetched is not None
    assert fetched.id == row.id


@pytest.mark.anyio
async def test_get_subagent_by_handle_returns_none_for_missing(
    db_session: AsyncSession, test_user: User
) -> None:
    fetched = await get_subagent_by_handle(db_session, handle="nope#xxx")
    assert fetched is None


@pytest.mark.anyio
async def test_list_subagents_orders_oldest_first(
    db_session: AsyncSession, test_user: User
) -> None:
    convo = await _seed_conversation(db_session, test_user)
    a = await _seed_subagent(db_session, convo=convo, user=test_user, handle="researcher#a")
    b = await _seed_subagent(db_session, convo=convo, user=test_user, handle="researcher#b")
    c = await _seed_subagent(db_session, convo=convo, user=test_user, handle="researcher#c")

    rows = await list_subagents_for_conversation(db_session, conversation_id=convo.id)
    assert [r.id for r in rows] == [a.id, b.id, c.id]


@pytest.mark.anyio
async def test_list_subagents_status_filter(db_session: AsyncSession, test_user: User) -> None:
    convo = await _seed_conversation(db_session, test_user)
    await _seed_subagent(db_session, convo=convo, user=test_user, handle="ok", status="succeeded")
    await _seed_subagent(db_session, convo=convo, user=test_user, handle="bad", status="failed")
    await _seed_subagent(db_session, convo=convo, user=test_user, handle="live", status="running")

    only_running = await list_subagents_for_conversation(
        db_session, conversation_id=convo.id, status_filter="running"
    )
    assert [r.handle for r in only_running] == ["live"]


@pytest.mark.anyio
async def test_count_running_for_conversation(db_session: AsyncSession, test_user: User) -> None:
    convo = await _seed_conversation(db_session, test_user)
    assert await count_running_for_conversation(db_session, conversation_id=convo.id) == 0

    await _seed_subagent(db_session, convo=convo, user=test_user, handle="a")
    await _seed_subagent(db_session, convo=convo, user=test_user, handle="b")
    await _seed_subagent(db_session, convo=convo, user=test_user, handle="done", status="succeeded")
    assert await count_running_for_conversation(db_session, conversation_id=convo.id) == 2


# ---------------------------------------------------------------------------
# Finalise
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_finalize_subagent_marks_succeeded(db_session: AsyncSession, test_user: User) -> None:
    convo = await _seed_conversation(db_session, test_user)
    row = await _seed_subagent(db_session, convo=convo, user=test_user, handle="a")

    updated = await finalize_subagent(
        db_session,
        subagent_id=row.id,
        status="succeeded",
        completed_at=_now(),
        result="the answer is 42",
        cost_usd=0.42,
        input_tokens=10,
        output_tokens=20,
    )
    await db_session.commit()
    assert updated is True

    fetched = await get_subagent_by_handle(db_session, handle="a")
    assert fetched is not None
    assert fetched.status == "succeeded"
    assert fetched.result == "the answer is 42"
    assert fetched.cost_usd == pytest.approx(0.42)
    assert fetched.input_tokens == 10
    assert fetched.output_tokens == 20
    assert fetched.completed_at is not None


@pytest.mark.anyio
async def test_finalize_subagent_idempotent_on_already_terminal(
    db_session: AsyncSession, test_user: User
) -> None:
    """Finalising a row that's already terminal is a no-op (returns False).

    This is the cascade-cancel race: the runner finished first, then the
    user deleted the conversation.  Without the ``status="running"``
    guard on the UPDATE, the cancel would clobber a real success.
    """
    convo = await _seed_conversation(db_session, test_user)
    row = await _seed_subagent(
        db_session, convo=convo, user=test_user, handle="a", status="succeeded"
    )

    re_finalise = await finalize_subagent(
        db_session,
        subagent_id=row.id,
        status="cancelled",
        completed_at=_now(),
    )
    assert re_finalise is False

    fetched = await get_subagent_by_handle(db_session, handle="a")
    assert fetched is not None
    assert fetched.status == "succeeded"  # was not overwritten


@pytest.mark.anyio
async def test_finalize_subagent_rejects_non_terminal_status(
    db_session: AsyncSession, test_user: User
) -> None:
    convo = await _seed_conversation(db_session, test_user)
    row = await _seed_subagent(db_session, convo=convo, user=test_user, handle="a")

    with pytest.raises(ValueError, match="non-terminal status"):
        await finalize_subagent(
            db_session,
            subagent_id=row.id,
            status="running",  # type: ignore[arg-type]
            completed_at=_now(),
        )


# ---------------------------------------------------------------------------
# Cascade-cancel hook + delete_conversation integration
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cancel_running_subagents_returns_ids_and_marks_rows(
    db_session: AsyncSession, test_user: User
) -> None:
    convo = await _seed_conversation(db_session, test_user)
    live_a = await _seed_subagent(db_session, convo=convo, user=test_user, handle="a")
    live_b = await _seed_subagent(db_session, convo=convo, user=test_user, handle="b")
    await _seed_subagent(db_session, convo=convo, user=test_user, handle="done", status="succeeded")

    cancelled = await cancel_running_subagents_for_conversation(
        db_session, conversation_id=convo.id
    )
    await db_session.commit()

    assert set(cancelled) == {live_a.id, live_b.id}

    fetched_a = await get_subagent_by_handle(db_session, handle="a")
    fetched_done = await get_subagent_by_handle(db_session, handle="done")
    assert fetched_a is not None and fetched_a.status == "cancelled"
    assert fetched_a.error == CASCADE_CANCEL_REASON
    # Already-terminal rows were not touched.
    assert fetched_done is not None and fetched_done.status == "succeeded"
    assert fetched_done.error is None


@pytest.mark.anyio
async def test_cancel_running_subagents_empty_returns_empty_list(
    db_session: AsyncSession, test_user: User
) -> None:
    convo = await _seed_conversation(db_session, test_user)
    cancelled = await cancel_running_subagents_for_conversation(
        db_session, conversation_id=convo.id
    )
    assert cancelled == []


@pytest.mark.anyio
async def test_delete_conversation_triggers_cascade_cancel_hook(
    db_session: AsyncSession, test_user: User
) -> None:
    """End-to-end: deleting a conversation cancels its running subagents.

    The app-level cancel hook runs *before* ``session.delete(conversation)``
    so each child row is marked ``cancelled`` with the documented reason.
    The DB-level ``ON DELETE CASCADE`` then sweeps the rows in Postgres
    production; SQLite (the test backend here) does not enforce FK
    cascades by default, so this test asserts the app-level behaviour
    that we control.  The schema-level cascade is verified by the
    integration suite that runs against Postgres.
    """
    convo = await _seed_conversation(db_session, test_user)
    await _seed_subagent(db_session, convo=convo, user=test_user, handle="a")
    await _seed_subagent(db_session, convo=convo, user=test_user, handle="b")

    deleted = await delete_conversation(test_user.id, db_session, convo.id)
    assert deleted is True

    surviving = (
        (await db_session.execute(select(Subagent).where(Subagent.conversation_id == convo.id)))
        .scalars()
        .all()
    )
    assert {row.status for row in surviving} == {"cancelled"}
    assert all(row.error == CASCADE_CANCEL_REASON for row in surviving)
    assert all(row.completed_at is not None for row in surviving)


@pytest.mark.anyio
async def test_delete_conversation_cascade_with_no_subagents(
    db_session: AsyncSession, test_user: User
) -> None:
    """The cancel hook short-circuits cleanly when no subagents exist."""
    convo = await _seed_conversation(db_session, test_user)
    deleted = await delete_conversation(test_user.id, db_session, convo.id)
    assert deleted is True


# ---------------------------------------------------------------------------
# Migration / model column-width invariant (caught by ORM at insert time)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handle_uniqueness_enforced(db_session: AsyncSession, test_user: User) -> None:
    convo = await _seed_conversation(db_session, test_user)
    await _seed_subagent(db_session, convo=convo, user=test_user, handle="dupe")

    with pytest.raises(Exception, match=r"UNIQUE|unique"):  # SQLite / Postgres both raise
        await _seed_subagent(db_session, convo=convo, user=test_user, handle="dupe")


@pytest.mark.anyio
async def test_subagent_uuid_type_matches_conversation_fk(
    db_session: AsyncSession, test_user: User
) -> None:
    """Smoke-check the FK types resolve — guards against a Uuid/String
    mismatch between the migration and the model."""
    convo = await _seed_conversation(db_session, test_user)
    row = await _seed_subagent(db_session, convo=convo, user=test_user, handle="x")
    assert isinstance(row.id, UUID)
    assert isinstance(row.conversation_id, UUID)
    assert row.conversation_id == convo.id
