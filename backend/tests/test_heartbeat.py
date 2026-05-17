"""Tests for the heartbeat parser, runner, and config helpers.

The runner is exercised against the in-memory SQLite session from
`conftest.py` so the assertion surface stays the same as the rest of
the chat-message CRUD tests.  APScheduler itself is not exercised here
— the lifespan is a thin wrapper around `add_job`/`shutdown`, and
exercising it would require either a real event loop with timing
assertions (flaky) or so much monkeypatching that the test stops
verifying anything real.  We test the things the scheduler calls into
(`run_heartbeat`) and trust APScheduler's own test suite for the rest.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.heartbeat import HEARTBEAT_MESSAGE_PREFIX, run_heartbeat
from app.core.heartbeat import (
    MIN_INTERVAL_SECONDS,
    HeartbeatCheck,
    HeartbeatConfig,
    parse_heartbeat_md,
)
from app.db import User
from app.models import ChatMessage, Conversation


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    """Insert a conversation row owned by `user`."""
    now = datetime(2025, 1, 1)
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="Heartbeat Test",
        created_at=now,
        updated_at=now,
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


# ── Parser ───────────────────────────────────────────────────


def test_parse_heartbeat_md_extracts_checks() -> None:
    """A well-formed front matter parses into a `HeartbeatConfig`."""
    text = """---
check s:
  - name: pulse
    interval_seconds: 1800
    prompt: |
      Report status.
---

Free-form body that is intentionally ignored by the parser.
""".replace("check s:", "checks:")
    config = parse_heartbeat_md(text)
    assert len(config.checks) == 1
    check = config.checks[0]
    assert check.name == "pulse"
    assert check.interval_seconds == 1800
    assert "Report status." in check.prompt


def test_parse_heartbeat_md_returns_empty_when_no_front_matter() -> None:
    """Pure markdown with no front matter yields an empty config (no crash)."""
    config = parse_heartbeat_md("# Heartbeat\n\nJust prose.\n")
    assert config.checks == []


def test_parse_heartbeat_md_rejects_sub_minute_interval() -> None:
    """The `MIN_INTERVAL_SECONDS` floor must be enforced at parse time."""
    text = f"""---
checks:
  - name: too-fast
    interval_seconds: {MIN_INTERVAL_SECONDS - 1}
    prompt: noop
---
"""
    with pytest.raises(ValueError, match="interval_seconds"):
        parse_heartbeat_md(text)


def test_parse_heartbeat_md_rejects_whitespace_name() -> None:
    """Names double as APScheduler job ids, so whitespace is rejected."""
    text = """---
checks:
  - name: "two words"
    interval_seconds: 3600
    prompt: noop
---
"""
    with pytest.raises(ValueError, match="whitespace"):
        parse_heartbeat_md(text)


def test_find_check_returns_named_or_none() -> None:
    """`HeartbeatConfig.find_check` is the lookup the manual endpoint uses."""
    config = HeartbeatConfig(
        checks=[
            HeartbeatCheck(name="alpha", interval_seconds=3600, prompt="a"),
            HeartbeatCheck(name="beta", interval_seconds=3600, prompt="b"),
        ]
    )
    found = config.find_check("beta")
    assert found is not None
    assert found.prompt == "b"
    assert config.find_check("missing") is None


# ── Runner ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_run_heartbeat_persists_tagged_assistant_message(
    db_session: AsyncSession, test_user: User
) -> None:
    """A heartbeat run writes one assistant message tagged with the prefix.

    This is the tracer assertion: the scheduler will call this function
    on every interval, and the chat UI's existing GET /messages path
    will surface the result without any frontend changes.
    """
    conv = await _make_conversation(db_session, test_user)
    check = HeartbeatCheck(
        name="pulse",
        interval_seconds=1800,
        prompt="Confirm aliveness.",
    )

    message_id = await run_heartbeat(
        db_session,
        user_id=test_user.id,
        conversation_id=conv.id,
        check=check,
    )

    result = await db_session.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    row = result.scalar_one()
    assert row.role == "assistant"
    assert row.assistant_status == "complete"
    assert row.content.startswith(HEARTBEAT_MESSAGE_PREFIX)
    assert "pulse" in row.content
    assert "Confirm aliveness." in row.content


@pytest.mark.anyio
async def test_run_heartbeat_bumps_conversation_updated_at(
    db_session: AsyncSession, test_user: User
) -> None:
    """The sidebar orders by `Conversation.updated_at` — heartbeats must bubble."""
    conv = await _make_conversation(db_session, test_user)
    old = conv.updated_at
    check = HeartbeatCheck(name="pulse", interval_seconds=1800, prompt="x")

    await run_heartbeat(
        db_session,
        user_id=test_user.id,
        conversation_id=conv.id,
        check=check,
    )
    await db_session.refresh(conv)

    assert conv.updated_at > old
