"""Tool factories for the bundled chat-artifact rendering plugin."""

from __future__ import annotations

from app.agents.tool_capabilities.core import make_artifact_tool as build_artifact_tool
from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext


def make_artifact_tool(ctx: ToolContext) -> AgentTool:
    """Return the surface-aware ``render_artifact`` tool."""
    return build_artifact_tool(surface=ctx.surface)
