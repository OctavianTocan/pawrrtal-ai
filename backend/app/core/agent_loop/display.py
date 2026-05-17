"""Agent-loop display metadata types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict


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
        payload = dict(self.formatter(arguments))
        payload.setdefault("icon", self.icon)
        payload.setdefault("label", self.label)
        payload.setdefault("present", self.label)
        payload.setdefault("compact", self.label)
        return ToolDisplayPayload(**payload)
