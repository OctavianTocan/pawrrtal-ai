"""Default tool permission checks for the provider-neutral agent loop."""

from __future__ import annotations

from typing import Any

from app.agents.types import AgentTool
from app.tools.workspace_files import matches_forbidden_filename

_PATH_GATED_TOOLS = frozenset({"read_file", "write_file"})


def default_tool_permission_check(
    tool: AgentTool,
    _tool_call_id: str,
    arguments: dict[str, Any],
) -> str | None:
    """Return a denial message when a tool call should be blocked.

    This is intentionally narrow: workspace file tools are still useful,
    but credential-shaped filenames should never be read into prompt context
    or overwritten by an agent turn.
    """
    if tool.name not in _PATH_GATED_TOOLS:
        return None
    raw_path = arguments.get("path")
    if not isinstance(raw_path, str) or not matches_forbidden_filename(raw_path):
        return None
    return (
        f"Tool '{tool.name}' cannot access '{raw_path}' because it looks like "
        "a credential or sensitive config file."
    )
