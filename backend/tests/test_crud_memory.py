"""Tests for the memory CRUD surface (#340)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.lcm.memory_crud import (
    find_similar_memories,
    insert_memory,
    list_memories_for_user,
    mark_memory_referenced,
)
from app.models import Memory


@pytest.mark.anyio
async def test_insert_memory_persists_with_defaults(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Default source is ``classifier``; default workspace / conversation NULL."""
    row = await insert_memory(
        db_session,
        test_user.id,
        kind="feedback",
        text="User prefers concise replies.",
    )
    assert row.kind == "feedback"
    assert row.source == "classifier"
    assert row.workspace_id is None
    assert row.conversation_id is None
    assert row.user_id == test_user.id


@pytest.mark.anyio
async def test_insert_memory_records_dreaming_source(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Dreaming-written rows carry the right provenance flag (#341 dependency)."""
    job_id = uuid.uuid4()
    row = await insert_memory(
        db_session,
        test_user.id,
        kind="project",
        text="Postgres for the cost ledger.",
        source="dreaming",
        provenance_job_id=job_id,
    )
    assert row.source == "dreaming"
    assert row.provenance_job_id == job_id


@pytest.mark.anyio
async def test_list_memories_returns_newest_first(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """The system-prompt assembler always wants the freshest top-K rows."""
    await insert_memory(db_session, test_user.id, kind="feedback", text="older")
    await insert_memory(db_session, test_user.id, kind="feedback", text="newer")
    rows = await list_memories_for_user(db_session, test_user.id, kind="feedback")
    assert [r.text for r in rows] == ["newer", "older"]


@pytest.mark.anyio
async def test_list_memories_filters_by_kind(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """The three kinds map to three distinct downstream consumers — keep them separable."""
    await insert_memory(db_session, test_user.id, kind="feedback", text="feedback row")
    await insert_memory(db_session, test_user.id, kind="project", text="project row")
    await insert_memory(db_session, test_user.id, kind="user", text="user row")

    feedback_rows = await list_memories_for_user(db_session, test_user.id, kind="feedback")
    assert {r.text for r in feedback_rows} == {"feedback row"}
    project_rows = await list_memories_for_user(db_session, test_user.id, kind="project")
    assert {r.text for r in project_rows} == {"project row"}


@pytest.mark.anyio
async def test_find_similar_returns_matching_substring(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """The cheap dedupe filter catches restatements via substring."""
    await insert_memory(
        db_session,
        test_user.id,
        kind="feedback",
        text="User prefers concise replies under 5 sentences.",
    )
    matches = await find_similar_memories(
        db_session,
        test_user.id,
        text="User prefers concise replies",
        kind="feedback",
    )
    assert len(matches) == 1


@pytest.mark.anyio
async def test_find_similar_respects_kind_partition(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """A ``project`` row with the same text doesn't dedupe a ``feedback`` write."""
    await insert_memory(db_session, test_user.id, kind="project", text="rate limit")
    matches = await find_similar_memories(
        db_session,
        test_user.id,
        text="rate limit",
        kind="feedback",
    )
    assert matches == []


@pytest.mark.anyio
async def test_mark_memory_referenced_updates_timestamp(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """The ``memory_query`` tool calls this whenever it surfaces a row."""
    row = await insert_memory(db_session, test_user.id, kind="user", text="prefers Pacific time")
    assert row.last_referenced_at is None
    await mark_memory_referenced(db_session, row.id)
    refreshed = await db_session.get(Memory, row.id)
    assert refreshed is not None
    assert refreshed.last_referenced_at is not None
