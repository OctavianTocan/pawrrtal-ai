"""Tests for the Beans-backed task plugin tools."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from app.plugins.beans_tasks.tools import (
    make_beans_complete_tool,
    make_beans_create_tool,
    make_beans_list_tool,
    make_beans_update_tool,
)
from app.plugins.tool_context import ToolContext


def _ctx(workspace_root: Path) -> ToolContext:
    return ToolContext(
        workspace_id=uuid.uuid4(),
        workspace_root=workspace_root,
        user_id=uuid.uuid4(),
    )


def test_beans_tools_create_list_update_and_complete(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    create = make_beans_create_tool(ctx)
    list_tool = make_beans_list_tool(ctx)
    update = make_beans_update_tool(ctx)
    complete = make_beans_complete_tool(ctx)

    created = asyncio.run(
        create.execute("call-1", title="Fix mobile login", body="Tap should sign in.")
    )
    assert created.startswith("Created bean pawrrtal-")

    listing = asyncio.run(list_tool.execute("call-2"))
    assert "Fix mobile login" in listing
    bean_id = listing.split()[1]

    updated = asyncio.run(update.execute("call-3", bean=bean_id, status="in-progress"))
    assert updated == f"Updated bean {bean_id}."

    completed = asyncio.run(complete.execute("call-4", bean="mobile login"))
    assert completed == f"Completed bean {bean_id}."

    open_listing = asyncio.run(list_tool.execute("call-5"))
    all_listing = asyncio.run(list_tool.execute("call-6", include_completed=True))

    assert "Fix mobile login" not in open_listing
    assert f"{bean_id} [completed/normal] Fix mobile login" in all_listing
    assert (tmp_path / ".beans").is_dir()


def test_beans_update_reports_ambiguous_matches(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    create = make_beans_create_tool(ctx)
    update = make_beans_update_tool(ctx)

    asyncio.run(create.execute("call-1", title="Follow up"))
    asyncio.run(create.execute("call-2", title="Follow through"))

    result = asyncio.run(update.execute("call-3", bean="Follow"))

    assert result.startswith("[invalid_path] Multiple beans matched")
