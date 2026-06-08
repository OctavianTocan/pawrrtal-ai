"""Tests for the Beans-backed task plugin tools."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

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


def _frontmatter(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    head = raw.split("---\n", 1)[1].partition("\n---\n")[0]
    parsed = yaml.safe_load(head)
    assert isinstance(parsed, dict)
    return parsed


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


def test_beans_create_quotes_yaml_sensitive_title(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    create = make_beans_create_tool(ctx)
    title = "Settings layout: align fields"

    asyncio.run(create.execute("call-1", title=title))

    path = next((tmp_path / ".beans").glob("*.md"))
    assert _frontmatter(path)["title"] == title
    assert "title: 'Settings layout: align fields'" in path.read_text(encoding="utf-8")


def test_beans_update_and_complete_preserve_structured_frontmatter(tmp_path: Path) -> None:
    root = tmp_path / ".beans"
    root.mkdir()
    path = root / "pawrrtal-abcd--existing.md"
    path.write_text(
        "\n".join(
            [
                "---",
                "# pawrrtal-abcd",
                "title: 'Existing: task'",
                "status: todo",
                "type: task",
                "priority: high",
                "tags:",
                "  - backend",
                "  - architecture",
                "blocked_by:",
                "  - pawrrtal-root",
                "created_at: 2026-06-08T00:00:00Z",
                "updated_at: 2026-06-08T00:00:00Z",
                "---",
                "",
                "Body.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    ctx = _ctx(tmp_path)
    update = make_beans_update_tool(ctx)
    complete = make_beans_complete_tool(ctx)

    asyncio.run(update.execute("call-1", bean="existing", status="in-progress"))
    asyncio.run(complete.execute("call-2", bean="existing"))

    meta = _frontmatter(path)
    assert meta["status"] == "completed"
    assert meta["tags"] == ["backend", "architecture"]
    assert meta["blocked_by"] == ["pawrrtal-root"]


def test_beans_list_rejects_invalid_status_filter(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    list_tool = make_beans_list_tool(ctx)

    result = asyncio.run(list_tool.execute("call-1", status="inprogress"))

    assert result == "[invalid_path] Unsupported bean status 'inprogress'."


def test_beans_create_regenerates_colliding_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / ".beans"
    root.mkdir()
    (root / "pawrrtal-aaaaaaaa--existing.md").write_text(
        "---\n# pawrrtal-aaaaaaaa\ntitle: Existing\nstatus: todo\n---\n\n",
        encoding="utf-8",
    )
    choices: Iterator[str] = iter("aaaaaaaabbbbbbbb")

    def choose_id_character(_alphabet: str) -> str:
        return next(choices)

    monkeypatch.setattr(secrets, "choice", choose_id_character)
    create = make_beans_create_tool(_ctx(tmp_path))

    result = asyncio.run(create.execute("call-1", title="New task"))

    assert result == "Created bean pawrrtal-bbbbbbbb: New task"
    assert (root / "pawrrtal-bbbbbbbb--new-task.md").exists()


def test_beans_update_reports_ambiguous_matches(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    create = make_beans_create_tool(ctx)
    update = make_beans_update_tool(ctx)

    asyncio.run(create.execute("call-1", title="Follow up"))
    asyncio.run(create.execute("call-2", title="Follow through"))

    result = asyncio.run(update.execute("call-3", bean="Follow"))

    assert result.startswith("[invalid_path] Multiple beans matched")
