"""Agent-loop display metadata types."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from app.core.agent_loop.types import AgentTool

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|secret|token|password|credential|authorization|content|payload|data)",
    re.IGNORECASE,
)


class ToolDisplayPayload(TypedDict, total=False):
    """User-facing display metadata for one tool call."""

    icon: str
    label: str
    present: str
    compact: str
    detail: str


ToolDisplayFormatter = Callable[[dict[str, Any]], ToolDisplayPayload]


@dataclass(frozen=True)
class ToolDisplay:
    """Formatter attached to an AgentTool for cross-surface tool-call UI."""

    icon: str
    label: str
    formatter: ToolDisplayFormatter

    def render(self, arguments: dict[str, Any]) -> ToolDisplayPayload:
        """Return a serializable display payload for *arguments*."""
        formatter_payload: dict[str, str] = dict(self.formatter(arguments))  # type: ignore[arg-type]
        formatter_payload.setdefault("icon", self.icon)
        formatter_payload.setdefault("label", self.label)
        formatter_payload.setdefault("present", self.label)
        formatter_payload.setdefault("compact", self.label)
        payload: ToolDisplayPayload = ToolDisplayPayload(**formatter_payload)  # type: ignore[typeddict-item]
        return payload


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


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))
