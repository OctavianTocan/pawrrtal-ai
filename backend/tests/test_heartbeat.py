"""Heartbeat: parser, conversation auto-create, delete guard, sync helper."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.heartbeat import (
    HeartbeatCheck,
    HeartbeatConfig,
    parse_heartbeat_md,
)
from app.crud.conversation import (
    HEARTBEAT_CONVERSATION_TITLE,
    HEARTBEAT_LABEL,
    delete_conversation,
    get_or_create_heartbeat_conversation,
)
from app.crud.heartbeat import JOB_NAME_PREFIX, sync_workspace_heartbeats
from app.infrastructure.database.legacy import User
from app.models import Conversation, Workspace

# ── Parser ───────────────────────────────────────────────────────────────


def test_parse_heartbeat_md_extracts_checks() -> None:
    """A well-formed front matter parses into a HeartbeatConfig."""
    text = """---
checks:
  - name: pulse
    cron: "0 9 * * *"
    prompt: |
      Daily heartbeat.
---

Free-form body below the fence is ignored by the parser.
"""
    config = parse_heartbeat_md(text)
    assert len(config.checks) == 1
    check = config.checks[0]
    assert check.name == "pulse"
    assert check.cron == "0 9 * * *"
    assert "Daily heartbeat." in check.prompt


def test_parse_heartbeat_md_returns_empty_when_no_front_matter() -> None:
    """Markdown with no front matter yields an empty config (no crash)."""
    config = parse_heartbeat_md("# Heartbeat\n\nJust prose.\n")
    assert config.checks == []


def test_parse_heartbeat_md_rejects_invalid_cron() -> None:
    """A malformed cron expression must fail at parse time."""
    text = """---
checks:
  - name: bad
    cron: "every fortnight"
    prompt: noop
---
"""
    with pytest.raises(ValueError, match="invalid cron expression"):
        parse_heartbeat_md(text)


def test_parse_heartbeat_md_rejects_whitespace_name() -> None:
    """Check names land in APScheduler job ids — no whitespace allowed."""
    text = """---
checks:
  - name: "two words"
    cron: "0 9 * * *"
    prompt: noop
---
"""
    with pytest.raises(ValueError, match="whitespace"):
        parse_heartbeat_md(text)


def test_find_check_returns_named_or_none() -> None:
    """HeartbeatConfig.find_check is the manual lookup used by the sync."""
    config = HeartbeatConfig(
        checks=[
            HeartbeatCheck(name="alpha", cron="0 9 * * *", prompt="a"),
            HeartbeatCheck(name="beta", cron="0 10 * * *", prompt="b"),
        ]
    )
    found = config.find_check("beta")
    assert found is not None
    assert found.prompt == "b"
    assert config.find_check("missing") is None


# ── Conversation helpers ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_or_create_heartbeat_conversation_creates_on_first_call(
    db_session: AsyncSession, test_user: User
) -> None:
    """First call creates the row labelled `heartbeat`."""
    conversation = await get_or_create_heartbeat_conversation(test_user.id, db_session)
    await db_session.commit()

    assert conversation.title == HEARTBEAT_CONVERSATION_TITLE
    assert HEARTBEAT_LABEL in (conversation.labels or [])
    assert conversation.user_id == test_user.id


@pytest.mark.anyio
async def test_get_or_create_heartbeat_conversation_is_idempotent(
    db_session: AsyncSession, test_user: User
) -> None:
    """Second call returns the existing row, not a duplicate."""
    first = await get_or_create_heartbeat_conversation(test_user.id, db_session)
    await db_session.commit()
    second = await get_or_create_heartbeat_conversation(test_user.id, db_session)
    await db_session.commit()

    assert first.id == second.id

    result = await db_session.execute(
        select(Conversation).where(Conversation.user_id == test_user.id)
    )
    rows = list(result.scalars())
    assert len(rows) == 1


# ── Delete guard ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_delete_conversation_blocks_heartbeat_label(
    db_session: AsyncSession, test_user: User
) -> None:
    """The CRUD layer rejects deletion of heartbeat-labelled rows.

    The DELETE route translates this to a 404 (same surface as
    "not yours"), which is the intended UX — the sidebar hides
    the delete action for heartbeat rows.
    """
    conversation = await get_or_create_heartbeat_conversation(test_user.id, db_session)
    await db_session.commit()

    deleted = await delete_conversation(test_user.id, db_session, conversation.id)
    assert deleted is False

    survivor = await db_session.get(Conversation, conversation.id)
    assert survivor is not None


@pytest.mark.anyio
async def test_delete_conversation_still_deletes_plain_rows(
    db_session: AsyncSession, test_user: User
) -> None:
    """Regression: the guard must only fire on heartbeat rows."""
    now = datetime(2025, 1, 1)
    plain = Conversation(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="Plain chat",
        created_at=now,
        updated_at=now,
        labels=[],
    )
    db_session.add(plain)
    await db_session.commit()

    deleted = await delete_conversation(test_user.id, db_session, plain.id)
    assert deleted is True
    assert await db_session.get(Conversation, plain.id) is None


# ── Sync helper ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_sync_workspace_heartbeats_registers_one_job_per_check(
    db_session: AsyncSession, test_user: User, tmp_path: Path
) -> None:
    """Each HEARTBEAT.md check turns into one JobScheduler.add_job call."""
    workspace = await _make_workspace(db_session, test_user, tmp_path)
    _write_heartbeat_md(
        tmp_path,
        """---
checks:
  - name: pulse
    cron: "0 9 * * *"
    prompt: Daily heartbeat.
  - name: weekly
    cron: "0 8 * * 1"
    prompt: Weekly review.
---
""",
    )
    scheduler = _FakeScheduler()

    result = await sync_workspace_heartbeats(
        session=db_session,
        user_id=test_user.id,
        workspace=workspace,
        scheduler=scheduler,  # type: ignore[arg-type]
    )

    assert result.jobs_created == 2
    assert result.jobs_removed == 0
    assert len(scheduler.added) == 2
    names = {call["name"] for call in scheduler.added}
    assert names == {
        f"{JOB_NAME_PREFIX}{workspace.id}:pulse",
        f"{JOB_NAME_PREFIX}{workspace.id}:weekly",
    }
    for call in scheduler.added:
        assert call["target_conversation_id"] == result.conversation_id
        assert call["target_chat_ids"] == []
        assert call["working_directory"] == workspace.path


@pytest.mark.anyio
async def test_sync_workspace_heartbeats_passes_telegram_chat_id(
    db_session: AsyncSession, test_user: User, tmp_path: Path
) -> None:
    """A linked Telegram chat is forwarded as target_chat_ids."""
    workspace = await _make_workspace(db_session, test_user, tmp_path)
    _write_heartbeat_md(
        tmp_path,
        """---
checks:
  - name: pulse
    cron: "0 9 * * *"
    prompt: Daily heartbeat.
---
""",
    )
    scheduler = _FakeScheduler()

    await sync_workspace_heartbeats(
        session=db_session,
        user_id=test_user.id,
        workspace=workspace,
        scheduler=scheduler,  # type: ignore[arg-type]
        telegram_chat_id="12345",
    )

    assert scheduler.added[0]["target_chat_ids"] == ["12345"]


@pytest.mark.anyio
async def test_sync_workspace_heartbeats_handles_missing_file(
    db_session: AsyncSession, test_user: User, tmp_path: Path
) -> None:
    """A workspace without HEARTBEAT.md syncs to zero jobs (no crash)."""
    workspace = await _make_workspace(db_session, test_user, tmp_path)
    scheduler = _FakeScheduler()

    result = await sync_workspace_heartbeats(
        session=db_session,
        user_id=test_user.id,
        workspace=workspace,
        scheduler=scheduler,  # type: ignore[arg-type]
    )

    assert result.jobs_created == 0
    assert result.jobs_removed == 0
    assert scheduler.added == []


# ── Helpers ──────────────────────────────────────────────────────────────


def _write_heartbeat_md(workspace_path: Path, content: str) -> None:
    """Drop a HEARTBEAT.md into a fake workspace dir for sync tests."""
    workspace_path.mkdir(parents=True, exist_ok=True)
    (workspace_path / "HEARTBEAT.md").write_text(content, encoding="utf-8")


async def _make_workspace(session: AsyncSession, user: User, root: Path) -> Workspace:
    """Create a Workspace row pointing at a real on-disk temp dir."""
    workspace = Workspace(
        id=uuid.uuid4(),
        user_id=user.id,
        name="Main",
        slug="main",
        path=str(root),
        is_default=True,
        created_at=datetime(2025, 1, 1),
    )
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)
    return workspace


class _FakeScheduler:
    """Records ``add_job`` + ``remove_job`` calls without touching APScheduler.

    The real ``JobScheduler.add_job`` validates the cron expression and
    inserts a row, both of which the sync test doesn't care about — we
    just need to see the call shape. Pre-existing rows aren't simulated
    here because the "remove stale" path is covered by its own scenario.
    """

    def __init__(self) -> None:
        self.added: list[dict[str, Any]] = []
        self.removed: list[uuid.UUID] = []
        # Make remove_job awaitable without dragging the real impl in.
        self.remove_job = AsyncMock(side_effect=self._record_remove)

    async def add_job(self, **kwargs: Any) -> Any:
        self.added.append(kwargs)
        return _FakeJobRow(job_id=uuid.uuid4(), name=kwargs.get("name", ""))

    async def _record_remove(self, *, session: AsyncSession, job_id: uuid.UUID) -> bool:
        del session
        self.removed.append(job_id)
        return True


class _FakeJobRow:
    """Tiny stand-in for the ``ScheduledJob`` row returned from add_job."""

    def __init__(self, *, job_id: uuid.UUID, name: str) -> None:
        self.id = job_id
        self.name = name
