"""Tests for the TASKS.md agent tools (#311 v1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.tools.tasks_md import (  # noqa: E402
    make_add_task_tool,
    make_complete_task_tool,
    make_list_tasks_tool,
)

pytestmark = pytest.mark.anyio


async def test_add_task_appends_to_tasks_md(tmp_path: Path) -> None:
    tool = make_add_task_tool(workspace_root=tmp_path)
    result = await tool.execute("call-1", description="Follow up with Acme", source="telegram")

    assert "Added task" in result
    body = (tmp_path / "TASKS.md").read_text()
    assert "Follow up with Acme" in body
    assert ", telegram)" in body
    assert "- [ ] Follow up with Acme" in body


async def test_add_task_rejects_empty_description(tmp_path: Path) -> None:
    tool = make_add_task_tool(workspace_root=tmp_path)
    result = await tool.execute("call-1", description="   ")
    assert "required" in result
    assert not (tmp_path / "TASKS.md").exists()


async def test_list_tasks_returns_open_only_by_default(tmp_path: Path) -> None:
    add = make_add_task_tool(workspace_root=tmp_path)
    list_ = make_list_tasks_tool(workspace_root=tmp_path)
    complete = make_complete_task_tool(workspace_root=tmp_path)

    await add.execute("c1", description="One")
    await add.execute("c2", description="Two")
    await complete.execute("c3", description="One")

    result = await list_.execute("c4")
    assert "Two" in result
    assert "One" not in result

    all_result = await list_.execute("c5", include_done=True)
    assert "Two" in all_result
    assert "One" in all_result
    assert "✓" in all_result


async def test_complete_task_marks_first_match(tmp_path: Path) -> None:
    add = make_add_task_tool(workspace_root=tmp_path)
    complete = make_complete_task_tool(workspace_root=tmp_path)

    await add.execute("c1", description="Read RFC 9110")
    await add.execute("c2", description="Read RFC 8259")

    result = await complete.execute("c3", description="RFC 8259")
    assert "Completed" in result
    body = (tmp_path / "TASKS.md").read_text()
    # The 8259 row is now done; the 9110 row stays open.
    assert "- [x] Read RFC 8259" in body
    assert "- [ ] Read RFC 9110" in body


async def test_complete_task_no_match_returns_message(tmp_path: Path) -> None:
    add = make_add_task_tool(workspace_root=tmp_path)
    complete = make_complete_task_tool(workspace_root=tmp_path)

    await add.execute("c1", description="Real task")
    result = await complete.execute("c2", description="nonexistent")
    assert "No open task matched" in result


async def test_list_tasks_empty_workspace_returns_friendly_message(tmp_path: Path) -> None:
    list_ = make_list_tasks_tool(workspace_root=tmp_path)
    result = await list_.execute("c1")
    assert "No open tasks" in result
