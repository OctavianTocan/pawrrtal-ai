"""``TASKS.md`` workspace-task tool (#311 v1).

Provides three small tools that read and edit a per-workspace
``TASKS.md`` file: ``add_task``, ``list_tasks``, and
``complete_task``. The format is plain Markdown checkboxes so the
file stays human-editable from any editor:

    # Tasks

    - [ ] Follow up on demo blockers (2026-05-18T10:00:00Z, telegram)
    - [x] Send weekly recap (2026-05-15T08:00:00Z, web) ✓ 2026-05-15T14:30:00Z

Each line carries: status (`- [ ]` / `- [x]`), description, creation
timestamp + source surface in parens, and an optional `✓ <timestamp>`
suffix for completed tasks. ``list_tasks`` parses the file and returns
a structured view; ``complete_task`` toggles the checkbox by line
prefix match.

The reminder / cron half of #311 is tracked separately — see #313.
This module only owns the local TASKS.md surface.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from pathlib import Path
from typing import Any

from app.agents.types import AgentTool
from app.tools.display import make_tool_display
from app.tools.errors import ToolError, ToolErrorCode

log = logging.getLogger(__name__)

_TASKS_FILENAME = "TASKS.md"
_TASKS_HEADER = "# Tasks\n\n"
# Recognise a TASKS.md row: ``- [ ] desc (date, source)`` (with an
# optional ``✓ date`` suffix for completed rows). Loose on whitespace
# so a human editing the file by hand doesn't break parsing.
_TASK_LINE_RE = re.compile(
    r"^\s*-\s*\[(?P<state>[ xX])\]\s*(?P<desc>.+?)\s*\((?P<created>[^,]+),\s*(?P<source>[^)]+)\)\s*(?:✓\s*(?P<done>.+?))?\s*$"
)


def _now_iso() -> str:
    """Return current UTC time in compact ISO-8601 form (no microseconds)."""
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_tasks_path(workspace_root: Path) -> Path:
    """Return the ``TASKS.md`` path inside *workspace_root*.

    The file is created on first write — :func:`_load_lines` returns
    an empty list when it doesn't exist yet, so ``list_tasks`` on a
    fresh workspace surfaces an empty list rather than an I/O error.
    """
    return Path(workspace_root) / _TASKS_FILENAME


def _load_lines(path: Path) -> list[str]:
    """Read the file as a list of lines; missing → empty."""
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _save_lines(path: Path, lines: list[str]) -> None:
    """Persist *lines* back to *path*, prepending the ``# Tasks`` header.

    Always rewrites the entire file so a manually-edited file's
    whitespace gets normalised on next save.
    """
    body = "\n".join(lines).rstrip()
    path.write_text(f"{_TASKS_HEADER}{body}\n" if body else _TASKS_HEADER, encoding="utf-8")


def _format_task_row(*, description: str, created: str, source: str) -> str:
    return f"- [ ] {description.strip()} ({created}, {source})"


def _parse_tasks(lines: list[str]) -> list[dict[str, Any]]:
    """Return a list of structured task records from raw file lines."""
    out: list[dict[str, Any]] = []
    for line in lines:
        match = _TASK_LINE_RE.match(line)
        if not match:
            continue
        out.append(
            {
                "description": match.group("desc"),
                "created": match.group("created"),
                "source": match.group("source"),
                "done": match.group("state").lower() == "x",
                "completed_at": match.group("done") or None,
                "raw": line,
            }
        )
    return out


def make_add_task_tool(*, workspace_root: Path) -> AgentTool:
    """Return the ``add_task`` :class:`AgentTool` bound to *workspace_root*."""

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        description = str(kwargs.get("description") or "").strip()
        source = str(kwargs.get("source") or "agent").strip() or "agent"
        if not description:
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "The 'description' argument is required and must be non-empty.",
            ).render()
        path = _resolve_tasks_path(workspace_root)
        lines = _load_lines(path)
        # Strip the auto-injected header if the file already exists —
        # we always re-render it in ``_save_lines``.
        if lines and lines[0].strip() == _TASKS_HEADER.strip():
            lines = lines[1:]
            # Also drop any leading blank line.
            if lines and not lines[0].strip():
                lines = lines[1:]
        new_row = _format_task_row(
            description=description,
            created=_now_iso(),
            source=source,
        )
        lines.append(new_row)
        _save_lines(path, lines)
        return f"Added task: {description!r}"

    return AgentTool(
        name="add_task",
        description=(
            "Append a task to TASKS.md in the user's workspace. "
            "Use when the user says 'add this to my tasks', 'remind me', "
            "'put this on my task list', or otherwise asks to record a "
            "follow-up item. For time-bound reminders (cron-backed), use "
            "the schedule tool instead (#313)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "What the user wants to remember. Keep it as a "
                        "short imperative phrase (e.g. 'Follow up with "
                        "Acme about Q3 contract')."
                    ),
                },
                "source": {
                    "type": "string",
                    "description": (
                        "Optional surface the request came from ('telegram', "
                        "'web', 'electron'). Defaults to 'agent' when unset."
                    ),
                },
            },
            "required": ["description"],
        },
        execute=execute,
        display=make_tool_display(
            icon="📝",
            label="Add task",
            present=lambda args: (
                f"📝 Adding task: {str(args.get('description') or '').strip()[:60] or '(empty)'}"
            ),
            compact=lambda args: f"add_task({str(args.get('description') or '')[:40]})",
        ),
    )


def make_list_tasks_tool(*, workspace_root: Path) -> AgentTool:
    """Return the ``list_tasks`` :class:`AgentTool` bound to *workspace_root*."""

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        include_done = bool(kwargs.get("include_done"))
        path = _resolve_tasks_path(workspace_root)
        tasks = _parse_tasks(_load_lines(path))
        if not include_done:
            tasks = [t for t in tasks if not t["done"]]
        if not tasks:
            return "No tasks found." if include_done else "No open tasks."
        rows = []
        for task in tasks:
            tick = "[x]" if task["done"] else "[ ]"
            done_suffix = f" ✓ {task['completed_at']}" if task["completed_at"] else ""
            rows.append(
                f"- {tick} {task['description']} ({task['created']}, {task['source']}){done_suffix}"
            )
        return "\n".join(rows)

    return AgentTool(
        name="list_tasks",
        description=(
            "Read TASKS.md from the user's workspace and return the open "
            "(or all) tasks as a Markdown checklist. Use when the user "
            "asks 'what's on my list', 'show my tasks', or before adding "
            "a task that might duplicate an existing one."
        ),
        parameters={
            "type": "object",
            "properties": {
                "include_done": {
                    "type": "boolean",
                    "description": (
                        "If true, include already-completed tasks. "
                        "Defaults to false — completed tasks are kept in "
                        "the file but hidden by default."
                    ),
                }
            },
            "required": [],
        },
        execute=execute,
        display=make_tool_display(
            icon="📋",
            label="List tasks",
            present=lambda args: (
                "📋 Listing tasks (incl. done)"
                if args.get("include_done")
                else "📋 Listing open tasks"
            ),
            compact=lambda args: (
                "list_tasks(include_done=True)" if args.get("include_done") else "list_tasks()"
            ),
        ),
    )


def make_complete_task_tool(*, workspace_root: Path) -> AgentTool:
    """Return the ``complete_task`` :class:`AgentTool` bound to *workspace_root*."""

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        needle = str(kwargs.get("description") or "").strip()
        if not needle:
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "The 'description' argument is required — pass a substring of the task to match.",
            ).render()
        path = _resolve_tasks_path(workspace_root)
        lines = _load_lines(path)
        matched = False
        new_lines: list[str] = []
        for line in lines:
            parsed = _TASK_LINE_RE.match(line)
            if parsed and not matched and needle.lower() in parsed.group("desc").lower():
                if parsed.group("state").lower() == "x":
                    # Already done — keep the line untouched.
                    new_lines.append(line)
                    matched = True
                    continue
                # Flip the checkbox + append a ✓ timestamp.
                desc = parsed.group("desc")
                created = parsed.group("created")
                source = parsed.group("source")
                new_lines.append(f"- [x] {desc} ({created}, {source}) ✓ {_now_iso()}")
                matched = True
                continue
            new_lines.append(line)
        if not matched:
            return f"No open task matched description {needle!r}."
        _save_lines(path, new_lines)
        return f"Completed task matching {needle!r}."

    return AgentTool(
        name="complete_task",
        description=(
            "Mark a task in TASKS.md as complete. Match by a substring of "
            "the task description (case-insensitive). The first matching "
            "open task is flipped to ``[x]`` and tagged with the current "
            "timestamp."
        ),
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "A substring of the task to complete. Match is "
                        "case-insensitive against the description text."
                    ),
                }
            },
            "required": ["description"],
        },
        execute=execute,
        display=make_tool_display(
            icon="✅",
            label="Complete task",
            present=lambda args: (
                f"✅ Completing task: {str(args.get('description') or '')[:60] or '(empty)'}"
            ),
            compact=lambda args: f"complete_task({str(args.get('description') or '')[:40]})",
        ),
    )
