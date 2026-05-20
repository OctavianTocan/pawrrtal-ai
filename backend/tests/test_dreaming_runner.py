"""Tests for the dreaming runner + scheduler (#341).

Uses a stubbed ``dream_fn`` so the pass runs without a live LLM —
exactly the pattern the agent-loop tests follow with
``ScriptedStreamFn``. The real persistence layer (SQLAlchemy +
SQLite) runs in the test DB so the lifecycle transitions
(``pending`` → ``running`` → ``completed`` / ``failed``), memory
inserts, and dedupe checks all exercise the production code path.

Each test passes a ``session_factory`` keyed to the test's
in-memory engine so the runner's own session reads the same data
the test seeded. Without that override the runner's
``async_session_maker`` would open a session against the
production engine and the test data would be invisible.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.dreaming import (
    run_dreaming_job,
    schedule_daily_rollup_dream,
    schedule_session_end_dream,
)
from app.crud.memory import insert_memory
from app.db import User
from app.models import ChatMessage, Conversation, DreamingJob, Memory


def _scripted_fn(payload: dict[str, object]) -> Callable[[str], Awaitable[str]]:
    """Return a ``DreamFn`` stub that always replies with ``payload`` as JSON."""
    encoded = json.dumps(payload)

    async def _stub(_prompt: str) -> str:
        return encoded

    return _stub


def _session_factory_for(db_session: AsyncSession):
    """Build a session factory bound to the test's in-memory engine.

    The runner's default factory is ``app.db.async_session_maker``,
    which targets the production engine. Tests rebind so the
    runner reads/writes through the same engine the fixture sets
    up; otherwise the runner would open an empty production
    session and see none of the seeded data.
    """
    engine = db_session.bind  # AsyncEngine attached to the test session
    test_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _factory() -> AsyncIterator[AsyncSession]:
        async with test_session_maker() as session:
            yield session

    return _factory


async def _seed_conversation(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    messages: list[tuple[str, str]],
) -> Conversation:
    """Insert a conversation + ordered messages and return the conversation row."""
    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Test conversation",
        created_at=now,
        updated_at=now,
    )
    db_session.add(conversation)
    await db_session.commit()
    for ordinal, (role, content) in enumerate(messages):
        db_session.add(
            ChatMessage(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                user_id=user_id,
                ordinal=ordinal,
                role=role,
                content=content,
                created_at=now,
                updated_at=now,
            )
        )
    await db_session.commit()
    return conversation


@pytest.mark.anyio
async def test_session_end_pass_writes_memories_and_completes(
    db_session: AsyncSession, test_user: User
) -> None:
    """Happy path: session_end pass writes consolidated memories + flips the job to completed."""
    factory = _session_factory_for(db_session)
    conversation = await _seed_conversation(
        db_session,
        user_id=test_user.id,
        messages=[
            ("user", "I always prefer concise replies."),
            ("assistant", "Noted — I'll keep responses short."),
        ],
    )
    payload = {
        "consolidated_memories": [
            {"kind": "user", "text": "Prefers concise replies."},
        ],
        "patterns": [{"text": "Repeated brevity request"}],
        "followups": [],
        "session_summary": "Short turn discussing response style.",
    }
    job_id = await schedule_session_end_dream(
        db_session,
        user_id=test_user.id,
        conversation_id=conversation.id,
        dream_fn=_scripted_fn(payload),
        session_factory=factory,
    )

    # ``schedule_session_end_dream`` spawns a background task that
    # may already have run before the next line lands. The runner
    # is idempotent on the ``status`` column — calling it again
    # against a row that's already ``completed`` is a no-op. We
    # call explicitly here so the test doesn't race the bg task
    # for the assertion phase.
    await run_dreaming_job(
        job_id,
        dream_fn=_scripted_fn(payload),
        session_factory=factory,
    )

    # Refresh from the same session that seeded the row so we
    # don't read a stale snapshot from before the runner committed.
    await db_session.commit()
    refreshed = await db_session.get(DreamingJob, job_id)
    await db_session.refresh(refreshed) if refreshed is not None else None
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.memories_written == 1
    assert refreshed.patterns_written == 1
    assert refreshed.session_summary == "Short turn discussing response style."
    assert refreshed.completed_at is not None

    memories = list(
        (await db_session.execute(select(Memory).where(Memory.user_id == test_user.id)))
        .scalars()
        .all()
    )
    assert len(memories) == 1
    assert memories[0].text == "Prefers concise replies."
    assert memories[0].source == "dreaming"
    assert memories[0].provenance_job_id == job_id


@pytest.mark.anyio
async def test_dedupe_skips_substring_duplicate(db_session: AsyncSession, test_user: User) -> None:
    """A consolidated memory whose substring already exists isn't re-inserted."""
    await insert_memory(
        db_session,
        test_user.id,
        kind="user",
        text="Prefers concise replies.",
        source="classifier",
    )

    factory = _session_factory_for(db_session)
    conversation = await _seed_conversation(
        db_session,
        user_id=test_user.id,
        messages=[("user", "Remember I want short answers.")],
    )
    job_id = await schedule_session_end_dream(
        db_session,
        user_id=test_user.id,
        conversation_id=conversation.id,
        session_factory=factory,
        dream_fn=_scripted_fn(
            {
                "consolidated_memories": [
                    {"kind": "user", "text": "Prefers concise replies."},
                ],
                "patterns": [],
                "followups": [],
                "session_summary": "",
            }
        ),
    )
    await run_dreaming_job(
        job_id,
        dream_fn=_scripted_fn(
            {
                "consolidated_memories": [
                    {"kind": "user", "text": "Prefers concise replies."},
                ],
                "patterns": [],
                "followups": [],
                "session_summary": "",
            }
        ),
        session_factory=factory,
    )

    await db_session.commit()
    refreshed = await db_session.get(DreamingJob, job_id)
    await db_session.refresh(refreshed) if refreshed is not None else None
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.memories_written == 0  # dedupe filtered the only candidate

    rows = list(
        (await db_session.execute(select(Memory).where(Memory.user_id == test_user.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1  # only the pre-seeded classifier memory


@pytest.mark.anyio
async def test_runner_marks_job_failed_on_dream_fn_error(
    db_session: AsyncSession, test_user: User
) -> None:
    """When the dream_fn raises, the job is marked failed with truncated error_text."""
    factory = _session_factory_for(db_session)
    conversation = await _seed_conversation(
        db_session,
        user_id=test_user.id,
        messages=[("user", "hi")],
    )
    job_id = await schedule_session_end_dream(
        db_session,
        user_id=test_user.id,
        conversation_id=conversation.id,
        session_factory=factory,
    )

    async def _exploding(_prompt: str) -> str:
        raise RuntimeError("LLM provider unreachable")

    await run_dreaming_job(job_id, dream_fn=_exploding, session_factory=factory)

    await db_session.commit()
    refreshed = await db_session.get(DreamingJob, job_id)
    await db_session.refresh(refreshed) if refreshed is not None else None
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert refreshed.error_text is not None
    assert "LLM provider unreachable" in refreshed.error_text


@pytest.mark.anyio
async def test_runner_is_idempotent_on_already_completed_job(
    db_session: AsyncSession, test_user: User
) -> None:
    """A second call against a completed job is a no-op (no double-insert).

    Important: schedule_*_dream spawns its own background task. If
    the test event loop runs the task before our explicit run, the
    explicit run must observe the terminal state and bail without
    re-writing memories.
    """
    factory = _session_factory_for(db_session)
    conversation = await _seed_conversation(
        db_session,
        user_id=test_user.id,
        messages=[("user", "test")],
    )
    job_id = await schedule_session_end_dream(
        db_session,
        user_id=test_user.id,
        conversation_id=conversation.id,
        session_factory=factory,
    )
    await run_dreaming_job(
        job_id,
        dream_fn=_scripted_fn(
            {
                "consolidated_memories": [{"kind": "user", "text": "Likes tests."}],
                "patterns": [],
                "followups": [],
                "session_summary": "",
            }
        ),
        session_factory=factory,
    )
    # Second call: status is already "completed", so the runner
    # should short-circuit and the memory count stays at 1.
    await run_dreaming_job(
        job_id,
        dream_fn=_scripted_fn(
            {
                "consolidated_memories": [{"kind": "user", "text": "Different text."}],
                "patterns": [],
                "followups": [],
                "session_summary": "",
            }
        ),
        session_factory=factory,
    )

    rows = list(
        (await db_session.execute(select(Memory).where(Memory.user_id == test_user.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].text == "Likes tests."


@pytest.mark.anyio
async def test_daily_rollup_scope_creates_a_pending_job_row(
    db_session: AsyncSession, test_user: User
) -> None:
    """The daily-rollup scheduler stamps the row with scope='daily_rollup'."""
    factory = _session_factory_for(db_session)
    job_id = await schedule_daily_rollup_dream(
        db_session,
        user_id=test_user.id,
        dream_fn=_scripted_fn({"consolidated_memories": []}),
        session_factory=factory,
    )
    row = await db_session.get(DreamingJob, job_id)
    assert row is not None
    assert row.scope == "daily_rollup"
    assert row.conversation_id is None
    assert row.user_id == test_user.id
