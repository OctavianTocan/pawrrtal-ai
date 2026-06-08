"""Tests for the Beans-backed task plugin tools."""

from __future__ import annotations

import asyncio
import os
import textwrap
import uuid
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


@pytest.fixture
def fake_beans_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    beans = bin_dir / "beans"
    beans.write_text(
        textwrap.dedent(
            r"""
            #!/usr/bin/env python3
            import re
            import sys
            from pathlib import Path

            import yaml

            ROOT = Path.cwd() / ".beans"


            def slug(title):
                return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:70] or "task"


            def split_frontmatter(raw):
                if not raw.startswith("---\n"):
                    return {}, raw
                _, rest = raw.split("---\n", 1)
                head, marker, body = rest.partition("\n---\n")
                if not marker:
                    return {}, raw
                parsed = yaml.safe_load(head)
                return parsed or {}, body


            def bean_id_from_path(path):
                return path.stem.split("--", 1)[0]


            def write_bean(path, bean_id, meta, body):
                path.parent.mkdir(parents=True, exist_ok=True)
                lines = ["---", f"# {bean_id}"]
                dumped = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
                if dumped and dumped != "{}":
                    lines.extend(dumped.splitlines())
                lines.extend(["---", "", body.strip(), ""])
                path.write_text("\n".join(lines), encoding="utf-8")


            def next_id():
                index = 1
                while True:
                    bean_id = f"pawrrtal-{index:08d}"
                    if not list(ROOT.glob(f"{bean_id}--*.md")):
                        return bean_id
                    index += 1


            def find_path(bean_id):
                matches = list(ROOT.glob(f"{bean_id}--*.md"))
                if not matches:
                    print(f"missing bean {bean_id}", file=sys.stderr)
                    sys.exit(2)
                return matches[0]


            def create(args):
                title = args[0]
                meta = {
                    "title": title,
                    "status": "todo",
                    "type": "task",
                    "priority": "normal",
                }
                body = ""
                index = 1
                while index < len(args):
                    flag = args[index]
                    value = args[index + 1]
                    if flag in ("-s", "--status"):
                        meta["status"] = value
                    elif flag in ("-p", "--priority"):
                        meta["priority"] = value
                    elif flag in ("-t", "--type"):
                        meta["type"] = value
                    elif flag in ("-d", "--description"):
                        body = value
                    else:
                        print(f"unsupported create flag {flag}", file=sys.stderr)
                        sys.exit(2)
                    index += 2
                bean_id = next_id()
                write_bean(ROOT / f"{bean_id}--{slug(title)}.md", bean_id, meta, body)
                print(f"Created bean {bean_id}: {title}")


            def update(args):
                bean_id = args[0]
                path = find_path(bean_id)
                meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
                index = 1
                while index < len(args):
                    flag = args[index]
                    value = args[index + 1]
                    if flag in ("-s", "--status"):
                        meta["status"] = value
                    elif flag in ("-p", "--priority"):
                        meta["priority"] = value
                    elif flag in ("-t", "--type"):
                        meta["type"] = value
                    elif flag == "--title":
                        meta["title"] = value
                    elif flag == "--body-append":
                        body = f"{body.rstrip()}\n\n{value}".strip()
                    elif flag == "--body-file":
                        body = Path(value).read_text(encoding="utf-8")
                    else:
                        print(f"unsupported update flag {flag}", file=sys.stderr)
                        sys.exit(2)
                    index += 2
                write_bean(path, bean_id_from_path(path), meta, body)
                status = "Completed" if meta.get("status") == "completed" else "Updated"
                print(f"{status} bean {bean_id}.")


            if len(sys.argv) < 2:
                print("missing command", file=sys.stderr)
                sys.exit(2)
            command = sys.argv[1]
            if command == "create":
                create(sys.argv[2:])
                sys.exit(0)
            elif command == "update":
                update(sys.argv[2:])
                sys.exit(0)
            else:
                print(f"unsupported command {command}", file=sys.stderr)
                sys.exit(2)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    beans.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")


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


def test_beans_tools_create_list_update_and_complete(
    tmp_path: Path,
    fake_beans_cli: None,
) -> None:
    ctx = _ctx(tmp_path)
    create = make_beans_create_tool(ctx)
    list_tool = make_beans_list_tool(ctx)
    update = make_beans_update_tool(ctx)
    complete = make_beans_complete_tool(ctx)

    async def run_scenario() -> tuple[str, str, str, str, str, str]:
        created = await create.execute(
            "call-1",
            title="Fix mobile login",
            body="Tap should sign in.",
        )
        listing = await list_tool.execute("call-2")
        bean_id = listing.split()[1]
        updated = await update.execute("call-3", bean=bean_id, status="in-progress")
        completed = await complete.execute("call-4", bean="mobile login")
        open_listing = await list_tool.execute("call-5")
        all_listing = await list_tool.execute("call-6", include_completed=True)
        return created, listing, updated, completed, open_listing, all_listing

    created, listing, updated, completed, open_listing, all_listing = asyncio.run(run_scenario())

    assert created == "Created bean pawrrtal-00000001: Fix mobile login"
    assert "Fix mobile login" in listing
    bean_id = listing.split()[1]
    assert updated == f"Updated bean {bean_id}."
    assert completed == f"Completed bean {bean_id}."

    assert "Fix mobile login" not in open_listing
    assert f"{bean_id} [completed/normal] Fix mobile login" in all_listing
    assert (tmp_path / ".beans").is_dir()


def test_beans_create_passes_metadata_to_cli(
    tmp_path: Path,
    fake_beans_cli: None,
) -> None:
    ctx = _ctx(tmp_path)
    create = make_beans_create_tool(ctx)
    title = "Settings layout: align fields"

    asyncio.run(create.execute("call-1", title=title, status="in-progress", priority="high"))

    path = next((tmp_path / ".beans").glob("*.md"))
    meta = _frontmatter(path)
    assert meta["title"] == title
    assert meta["status"] == "in-progress"
    assert meta["priority"] == "high"


def test_beans_update_and_complete_preserve_structured_frontmatter(
    tmp_path: Path,
    fake_beans_cli: None,
) -> None:
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

    async def run_scenario() -> None:
        await update.execute("call-1", bean="existing", status="in-progress")
        await complete.execute("call-2", bean="existing")

    asyncio.run(run_scenario())

    meta = _frontmatter(path)
    assert meta["status"] == "completed"
    assert meta["tags"] == ["backend", "architecture"]
    assert meta["blocked_by"] == ["pawrrtal-root"]


def test_beans_update_replaces_body_through_cli(
    tmp_path: Path,
    fake_beans_cli: None,
) -> None:
    ctx = _ctx(tmp_path)
    create = make_beans_create_tool(ctx)
    update = make_beans_update_tool(ctx)

    async def run_scenario() -> str:
        await create.execute("call-1", title="Body task", body="Old body.")
        return await update.execute("call-2", bean="Body task", body="New body.")

    result = asyncio.run(run_scenario())

    assert result == "Updated bean pawrrtal-00000001."
    assert "New body." in next((tmp_path / ".beans").glob("*.md")).read_text(encoding="utf-8")


def test_beans_list_rejects_invalid_status_filter(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    list_tool = make_beans_list_tool(ctx)

    result = asyncio.run(list_tool.execute("call-1", status="inprogress"))

    assert result == "[invalid_path] Unsupported bean status 'inprogress'."


def test_beans_list_accepts_workspace_statuses(tmp_path: Path) -> None:
    root = tmp_path / ".beans"
    root.mkdir()
    for bean_id, status in (
        ("pawrrtal-draft", "draft"),
        ("pawrrtal-review", "in-review"),
    ):
        (root / f"{bean_id}--task.md").write_text(
            "\n".join(
                [
                    "---",
                    f"# {bean_id}",
                    f"title: {status} task",
                    f"status: {status}",
                    "priority: normal",
                    "---",
                    "",
                    "Body.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    list_tool = make_beans_list_tool(_ctx(tmp_path))

    draft = asyncio.run(list_tool.execute("call-1", status="draft"))
    in_review = asyncio.run(list_tool.execute("call-2", status="in-review"))

    assert "pawrrtal-draft [draft/normal] draft task" in draft
    assert "pawrrtal-review [in-review/normal] in-review task" in in_review


def test_beans_list_skips_malformed_frontmatter(tmp_path: Path) -> None:
    root = tmp_path / ".beans"
    root.mkdir()
    (root / "pawrrtal-bad--broken.md").write_text(
        "---\ntitle: [broken\n---\n\nBroken body.\n",
        encoding="utf-8",
    )
    (root / "pawrrtal-good--valid.md").write_text(
        "\n".join(
            [
                "---",
                "# pawrrtal-good",
                "title: Valid task",
                "status: todo",
                "priority: high",
                "---",
                "",
                "Valid body.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    list_tool = make_beans_list_tool(_ctx(tmp_path))

    result = asyncio.run(list_tool.execute("call-1"))

    assert "pawrrtal-good [todo/high] Valid task" in result
    assert "pawrrtal-bad" not in result


def test_beans_create_reports_missing_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    create = make_beans_create_tool(_ctx(tmp_path))

    result = asyncio.run(create.execute("call-1", title="New task"))

    assert result == "[not_found] beans CLI is not installed or not on PATH."


def test_beans_update_reports_ambiguous_matches(
    tmp_path: Path,
    fake_beans_cli: None,
) -> None:
    ctx = _ctx(tmp_path)
    create = make_beans_create_tool(ctx)
    update = make_beans_update_tool(ctx)

    async def run_scenario() -> str:
        await create.execute("call-1", title="Follow up")
        await create.execute("call-2", title="Follow through")
        return await update.execute("call-3", bean="Follow")

    result = asyncio.run(run_scenario())

    assert result.startswith("[invalid_path] Multiple beans matched")
