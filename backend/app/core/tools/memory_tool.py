"""Structured memory tool for persistent cross-conversation context.

Manages two workspace-root files:
- ``USER.md`` — facts about the person the agent is helping.
- ``MEMORY.md`` — environment facts, conventions, and tool quirks.

Entries are delimited by ``§`` so add/replace/remove are atomic.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.tools.display import make_tool_display

log = logging.getLogger(__name__)

_SECTION_DELIMITER = "\n§\n"

_USER_MD = "USER.md"
_MEMORY_MD = "MEMORY.md"

_USER_MD_CAP_CHARS = 1375
_MEMORY_MD_CAP_CHARS = 2200

_TARGET_CONFIG: dict[str, tuple[str, int]] = {
    "user": (_USER_MD, _USER_MD_CAP_CHARS),
    "memory": (_MEMORY_MD, _MEMORY_MD_CAP_CHARS),
}

_VALID_ACTIONS = frozenset({"add", "replace", "remove"})

_DESCRIPTION = (
    "Manage persistent memory that survives across conversations. "
    "Memories are injected into your system prompt on every future turn.\n\n"
    "Two targets:\n"
    "- `user`: facts about the person you're helping (name, role, preferences). "
    "Cap: 1375 chars.\n"
    "- `memory`: your notes about the environment, conventions, tool quirks. "
    "Cap: 2200 chars.\n\n"
    "Three actions:\n"
    "- `add`: append a new entry.\n"
    "- `replace`: swap an existing entry (provide `old_text` and `content`).\n"
    "- `remove`: delete an existing entry (provide `old_text`).\n\n"
    "Keep entries concise — one fact per entry. Curate aggressively when near the cap."
)

_FIRST_40_CHARS = 40


def _result(*, success: bool, rendered_state: str = "", error: str = "") -> str:
    payload: dict[str, Any] = {"success": success, "rendered_state": rendered_state}
    if error:
        payload["error"] = error
    return json.dumps(payload)


def _read_entries(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return text.split(_SECTION_DELIMITER)


def _write_entries(path: Path, entries: list[str]) -> None:
    content = _SECTION_DELIMITER.join(entries)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        tmp_path.replace(path)
    except BaseException:
        os.close(fd) if not os.get_inheritable(fd) else None
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _render_state(entries: list[str]) -> str:
    return _SECTION_DELIMITER.join(entries)


def make_memory_tool(*, workspace_root: Path) -> AgentTool:
    """Return the ``memory`` AgentTool scoped to *workspace_root*."""
    root = Path(workspace_root).resolve()

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        target = kwargs.get("target", "")
        content = kwargs.get("content", "")
        old_text = kwargs.get("old_text", "")

        if action not in _VALID_ACTIONS:
            return _result(success=False, error=f"Unknown action: {action!r}")
        if target not in _TARGET_CONFIG:
            return _result(success=False, error=f"Unknown target: {target!r}")

        filename, cap = _TARGET_CONFIG[target]
        path = root / filename
        entries = _read_entries(path)

        if action == "add":
            return _handle_add(path, entries, content, cap)
        if action == "replace":
            return _handle_replace(path, entries, old_text, content)
        return _handle_remove(path, entries, old_text)

    return AgentTool(
        name="memory",
        description=_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "replace", "remove"],
                    "description": "The operation to perform.",
                },
                "target": {
                    "type": "string",
                    "enum": ["user", "memory"],
                    "description": "Which memory file to operate on.",
                },
                "content": {
                    "type": "string",
                    "description": "The text to add or replace with.",
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text of the entry to replace or remove.",
                },
            },
            "required": ["action", "target"],
        },
        execute=execute,
        display=make_tool_display(
            icon="🧠",
            label="Memory",
            present=lambda args: (
                f"🧠 {args.get('action', '').title()}ing {args.get('target', '')} memory: "
                f"{(args.get('content') or args.get('old_text') or '')[:_FIRST_40_CHARS]}"
            ),
            compact=lambda args: (
                f"memory({args.get('action')}, {args.get('target')})"
            ),
        ),
    )


def _handle_add(
    path: Path, entries: list[str], content: str, cap: int
) -> str:
    if not content:
        return _result(success=False, error="'content' is required for add.")
    new_entries = [*entries, content]
    total = len(_render_state(new_entries))
    if total > cap:
        return _result(
            success=False,
            error=f"Would exceed cap ({total}/{cap} chars). Curate existing entries first.",
            rendered_state=_render_state(entries),
        )
    _write_entries(path, new_entries)
    return _result(success=True, rendered_state=_render_state(new_entries))


def _handle_replace(
    path: Path, entries: list[str], old_text: str, content: str
) -> str:
    if not old_text:
        return _result(success=False, error="'old_text' is required for replace.")
    if not content:
        return _result(success=False, error="'content' is required for replace.")
    for i, entry in enumerate(entries):
        if entry.strip() == old_text.strip():
            entries[i] = content
            _write_entries(path, entries)
            return _result(success=True, rendered_state=_render_state(entries))
    return _result(success=False, error=f"No entry matching: {old_text!r}")


def _handle_remove(
    path: Path, entries: list[str], old_text: str
) -> str:
    if not old_text:
        return _result(success=False, error="'old_text' is required for remove.")
    for i, entry in enumerate(entries):
        if entry.strip() == old_text.strip():
            entries.pop(i)
            _write_entries(path, entries)
            return _result(success=True, rendered_state=_render_state(entries))
    return _result(success=False, error=f"No entry matching: {old_text!r}")
