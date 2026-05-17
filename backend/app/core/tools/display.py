"""Shared user-facing display metadata for agent tools."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from app.core.agent_loop.display import ToolDisplay, ToolDisplayPayload

if TYPE_CHECKING:
    from app.core.agent_loop.types import AgentTool

_MAX_VALUE_CHARS = 72
_MAX_PATH_CHARS = 64
_MAX_QUERY_CHARS = 96
_PATH_TAIL_PARTS = 2

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|secret|token|password|credential|authorization|content|payload|data)",
    re.IGNORECASE,
)


def make_tool_display(
    *,
    icon: str,
    label: str,
    present: Callable[[dict[str, Any]], str],
    compact: Callable[[dict[str, Any]], str],
    detail: Callable[[dict[str, Any]], str | None] | None = None,
) -> ToolDisplay:
    """Build a reusable :class:`ToolDisplay`."""

    def formatter(arguments: dict[str, Any]) -> ToolDisplayPayload:
        payload = ToolDisplayPayload(
            icon=icon,
            label=label,
            present=present(arguments),
            compact=compact(arguments),
        )
        if detail is not None:
            detail_text = detail(arguments)
            if detail_text:
                payload["detail"] = detail_text
        return payload

    return ToolDisplay(icon=icon, label=label, formatter=formatter)


def render_tool_display(tool: AgentTool | None, arguments: dict[str, Any]) -> ToolDisplayPayload:
    """Render a display payload for a known tool or return a generic fallback."""
    if tool is not None and tool.display is not None:
        return tool.display.render(arguments)
    name = tool.name if tool is not None else "tool"
    return fallback_tool_display(name, arguments)


def tool_display_map(tools: list[AgentTool]) -> dict[str, ToolDisplay]:
    """Return display formatters keyed by bare tool name."""
    return {tool.name: tool.display for tool in tools if tool.display is not None}


def render_display_from_map(
    display_by_name: dict[str, ToolDisplay],
    name: str,
    arguments: dict[str, Any],
) -> ToolDisplayPayload:
    """Render display metadata using a name-keyed formatter map."""
    display = display_by_name.get(name)
    if display is not None:
        return display.render(arguments)
    return fallback_tool_display(name, arguments)


def fallback_tool_display(name: str, arguments: dict[str, Any]) -> ToolDisplayPayload:
    """Generic display for tools without custom display metadata."""
    label = friendly_tool_name(name)
    keys = visible_argument_keys(arguments)
    suffix = f" ({', '.join(keys)})" if keys else ""
    return ToolDisplayPayload(
        icon="🛠",
        label=label,
        present=f"🛠 Running {label}{suffix}",
        compact=f"{label}{suffix}",
    )


def friendly_tool_name(name: str) -> str:
    """Convert a machine tool name to a compact display label."""
    bare = name.rsplit("__", 1)[-1]
    return bare.replace("_", " ").replace("-", " ").strip().title() or "Tool"


def visible_argument_keys(arguments: dict[str, Any]) -> list[str]:
    """Return keys that are safe and useful to show in generic fallbacks."""
    return [str(key) for key in arguments if not _is_sensitive_key(str(key))]


def summarize_path(value: Any) -> str:
    """Return a compact path summary."""
    raw = str(value or ".").strip() or "."
    normalized = raw.replace("\\", "/")
    if len(normalized) <= _MAX_PATH_CHARS:
        return normalized
    path = PurePosixPath(normalized)
    parts = path.parts
    if len(parts) >= _PATH_TAIL_PARTS:
        tail = "/".join(parts[-_PATH_TAIL_PARTS:])
        return f".../{tail}"
    return truncate_text(normalized, _MAX_PATH_CHARS)


def summarize_query(value: Any) -> str:
    """Return a quoted, truncated query summary."""
    text = truncate_text(str(value or "").strip(), _MAX_QUERY_CHARS)
    return f'"{text}"' if text else "the query"


def summarize_title(value: Any, fallback: str) -> str:
    """Return a quoted title when available, otherwise *fallback*."""
    text = truncate_text(str(value or "").strip(), _MAX_VALUE_CHARS)
    return f'"{text}"' if text else fallback


def truncate_text(text: str, max_chars: int = _MAX_VALUE_CHARS) -> str:
    """Trim whitespace and truncate with an ellipsis when needed."""
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 1]}…"


def display_safe_value(key: str, value: Any) -> str:
    """Return a safe inline value for optional details."""
    if _is_sensitive_key(key):
        return "hidden"
    if isinstance(value, str):
        return truncate_text(value)
    if isinstance(value, bool | int | float):
        return str(value)
    return truncate_text(str(value))


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))
