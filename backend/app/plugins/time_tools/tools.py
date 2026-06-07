"""Tool factories for the bundled time tools plugin."""

from __future__ import annotations

from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext
from app.tools.now import make_now_tool as build_now_tool


def make_now_tool(_ctx: ToolContext) -> AgentTool:
    """Return the ``now`` tool."""
    return build_now_tool()
