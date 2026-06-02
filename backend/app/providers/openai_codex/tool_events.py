"""Codex thread-item helpers for user-visible tool stream events."""

from __future__ import annotations

from typing import Any, cast

from app.providers.base import StreamEvent

_OUTPUT_PREVIEW_MAX_CHARS = 2000
_COMMAND_LABEL_MAX_CHARS = 80
_COMMAND_LABEL_TRUNCATE_AT = 77


def plan_text(plan: Any, explanation: str | None = None) -> str:
    """Render a Codex plan update as compact user-visible text."""
    lines: list[str] = []
    if explanation:
        lines.append(explanation)
    if isinstance(plan, list):
        for step in plan:
            status = str(
                getattr(getattr(step, "status", None), "value", getattr(step, "status", ""))
            )
            label = str(getattr(step, "step", "") or "")
            if label:
                prefix = f"{status}: " if status else ""
                lines.append(f"{prefix}{label}")
    elif plan:
        lines.append(str(plan))
    return "\n".join(lines).strip()


def tool_use_for_item(item: Any) -> StreamEvent | None:  # noqa: PLR0911
    """Translate a Codex thread item into a Pawrrtal ``tool_use`` event."""
    inner = _item_root(item)
    item_id = _item_id(inner)
    item_type = _item_type(inner)
    if not item_id:
        return None
    if item_type == "commandExecution":
        command = str(getattr(inner, "command", "") or "shell command")
        label = _command_label(command)
        return cast(
            StreamEvent,
            {
                "type": "tool_use",
                "name": "codex_command",
                "tool_use_id": item_id,
                "input": {"command": command},
                "display": _tool_display(
                    icon="🖥",
                    present=f"Running {label}",
                    compact=f"Ran {label}",
                ),
            },
        )
    if item_type == "fileChange":
        changes = getattr(inner, "changes", None) or []
        count = len(changes) if isinstance(changes, list) else 0
        return cast(
            StreamEvent,
            {
                "type": "tool_use",
                "name": "codex_file_change",
                "tool_use_id": item_id,
                "input": {"changes": count},
                "display": _tool_display(
                    icon="📝",
                    present=f"Editing {count} file{'s' if count != 1 else ''}",
                    compact=f"Edited {count} file{'s' if count != 1 else ''}",
                ),
            },
        )
    if item_type == "mcpToolCall":
        server = str(getattr(inner, "server", "") or "mcp")
        tool = str(getattr(inner, "tool", "") or "tool")
        return cast(
            StreamEvent,
            {
                "type": "tool_use",
                "name": f"{server}.{tool}",
                "tool_use_id": item_id,
                "input": {"server": server, "tool": tool},
                "display": _tool_display(
                    icon="🔌",
                    present=f"Calling {server}.{tool}",
                    compact=f"Called {server}.{tool}",
                ),
            },
        )
    if item_type == "webSearch":
        query = str(getattr(inner, "query", "") or "web search")
        return cast(
            StreamEvent,
            {
                "type": "tool_use",
                "name": "codex_web_search",
                "tool_use_id": item_id,
                "input": {"query": query},
                "display": _tool_display(
                    icon="🔎",
                    present=f"Searching {query}",
                    compact=f"Searched {query}",
                ),
            },
        )
    if item_type == "dynamicToolCall":
        tool = str(getattr(inner, "tool", "") or "dynamic tool")
        return cast(
            StreamEvent,
            {
                "type": "tool_use",
                "name": tool,
                "tool_use_id": item_id,
                "input": {"tool": tool},
                "display": _tool_display(
                    icon="🛠",
                    present=f"Running {tool}",
                    compact=f"Ran {tool}",
                ),
            },
        )
    return None


def tool_result_for_item(item: Any) -> StreamEvent | None:
    """Translate a completed Codex thread item into a ``tool_result`` event."""
    inner = _item_root(item)
    item_id = _item_id(inner)
    item_type = _item_type(inner)
    if not item_id:
        return None
    if item_type == "commandExecution":
        output = str(getattr(inner, "aggregated_output", None) or "")
        status = str(getattr(getattr(inner, "status", None), "value", getattr(inner, "status", "")))
        exit_code = getattr(inner, "exit_code", None)
        content = truncate_tool_output(output)
        if exit_code is not None:
            content = f"exit_code={exit_code}\n{content}".strip()
        return {
            "type": "tool_result",
            "tool_use_id": item_id,
            "content": content,
            "is_error": status in {"failed", "declined"} or (exit_code not in (None, 0)),
        }
    if item_type == "fileChange":
        status = str(getattr(getattr(inner, "status", None), "value", getattr(inner, "status", "")))
        return {
            "type": "tool_result",
            "tool_use_id": item_id,
            "content": status or "file change complete",
            "is_error": status in {"failed", "rejected"},
        }
    if item_type == "mcpToolCall":
        status = str(getattr(getattr(inner, "status", None), "value", getattr(inner, "status", "")))
        error = getattr(inner, "error", None)
        content = str(getattr(error, "message", "") or status or "tool call complete")
        return {
            "type": "tool_result",
            "tool_use_id": item_id,
            "content": truncate_tool_output(content),
            "is_error": bool(error) or status == "failed",
        }
    if item_type in {"dynamicToolCall", "webSearch"}:
        status = str(getattr(getattr(inner, "status", None), "value", getattr(inner, "status", "")))
        return {
            "type": "tool_result",
            "tool_use_id": item_id,
            "content": status or "complete",
            "is_error": status == "failed",
        }
    return None


def truncate_tool_output(text: str, max_chars: int = _OUTPUT_PREVIEW_MAX_CHARS) -> str:
    """Bound noisy Codex tool output before rendering/persisting it."""
    value = text.strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip()


def _tool_display(
    *,
    icon: str,
    present: str,
    compact: str,
    detail: str | None = None,
) -> dict[str, str]:
    payload = {"icon": icon, "label": compact, "present": present, "compact": compact}
    if detail:
        payload["detail"] = detail
    return payload


def _item_root(item: Any) -> Any:
    return getattr(item, "root", item)


def _item_id(item: Any) -> str:
    return str(getattr(_item_root(item), "id", "") or "")


def _item_type(item: Any) -> str:
    return str(getattr(_item_root(item), "type", "") or type(_item_root(item)).__name__)


def _command_label(command: str) -> str:
    value = " ".join(command.split())
    if len(value) <= _COMMAND_LABEL_MAX_CHARS:
        return value
    return value[:_COMMAND_LABEL_TRUNCATE_AT].rstrip() + "..."
