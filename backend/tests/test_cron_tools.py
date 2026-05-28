"""Tests for the cron scheduling agent tools (#313)."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.tools import cron_tools  # noqa: E402

pytestmark = pytest.mark.anyio

_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_JOB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


async def test_cron_create_returns_disabled_when_scheduler_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cron_tools, "get_active_scheduler", lambda: None)
    tool = cron_tools.make_reminder_schedule_tool(user_id=_USER_ID)
    result = await tool.execute(
        "call-1",
        name="daily standup",
        cron_expression="0 9 * * 1-5",
        prompt="Remind me about standup",
    )
    assert "[scheduler_disabled]" in result


async def test_cron_create_rejects_missing_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = AsyncMock()
    monkeypatch.setattr(cron_tools, "get_active_scheduler", lambda: scheduler)
    tool = cron_tools.make_reminder_schedule_tool(user_id=_USER_ID)
    result = await tool.execute("call-1", name="x")
    assert "requires" in result.lower()
    scheduler.add_job.assert_not_called()


async def test_cron_create_invokes_scheduler_add_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = AsyncMock()
    row = MagicMock()
    row.id = _JOB_ID
    row.name = "daily standup"
    row.cron_expression = "0 9 * * 1-5"
    scheduler.add_job.return_value = row
    monkeypatch.setattr(cron_tools, "get_active_scheduler", lambda: scheduler)
    conv_id = uuid.uuid4()
    tool = cron_tools.make_reminder_schedule_tool(user_id=_USER_ID, conversation_id=conv_id)
    result = await tool.execute(
        "call-1",
        name="daily standup",
        cron_expression="0 9 * * 1-5",
        prompt="Remind me",
    )
    assert str(_JOB_ID) in result
    scheduler.add_job.assert_awaited_once()
    kwargs = scheduler.add_job.await_args.kwargs
    assert kwargs["user_id"] == _USER_ID
    assert kwargs["name"] == "daily standup"
    assert kwargs["cron_expression"] == "0 9 * * 1-5"
    assert kwargs["prompt"] == "Remind me"
    assert kwargs["target_conversation_id"] == conv_id


async def test_cron_create_surfaces_invalid_cron_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = AsyncMock()
    scheduler.add_job.side_effect = ValueError("bad cron")
    monkeypatch.setattr(cron_tools, "get_active_scheduler", lambda: scheduler)
    tool = cron_tools.make_reminder_schedule_tool(user_id=_USER_ID)
    result = await tool.execute(
        "call-1",
        name="oops",
        cron_expression="not a cron",
        prompt="prompt",
    )
    assert "[invalid_schedule]" in result


async def test_cron_list_returns_disabled_when_scheduler_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cron_tools, "get_active_scheduler", lambda: None)
    tool = cron_tools.make_reminder_list_tool(user_id=_USER_ID)
    result = await tool.execute("call-1")
    assert "[scheduler_disabled]" in result


async def test_cron_delete_rejects_empty_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = AsyncMock()
    monkeypatch.setattr(cron_tools, "get_active_scheduler", lambda: scheduler)
    tool = cron_tools.make_reminder_cancel_tool(user_id=_USER_ID)
    result = await tool.execute("call-1", job_id="")
    assert "requires" in result.lower()
    scheduler.remove_job.assert_not_called()


async def test_cron_delete_rejects_malformed_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = AsyncMock()
    monkeypatch.setattr(cron_tools, "get_active_scheduler", lambda: scheduler)
    tool = cron_tools.make_reminder_cancel_tool(user_id=_USER_ID)
    result = await tool.execute("call-1", job_id="not-a-uuid")
    assert "[invalid_job_id]" in result


async def test_cron_delete_disabled_when_scheduler_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cron_tools, "get_active_scheduler", lambda: None)
    tool = cron_tools.make_reminder_cancel_tool(user_id=_USER_ID)
    result = await tool.execute("call-1", job_id=str(_JOB_ID))
    assert "[scheduler_disabled]" in result
