"""Tool factories for the bundled time tools plugin."""

from __future__ import annotations

from app.agents.tool_capabilities.core import make_now_tool as build_now_tool
from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext


def make_now_tool(_ctx: ToolContext) -> AgentTool:
    """Return the ``now`` tool."""
    return build_now_tool()
