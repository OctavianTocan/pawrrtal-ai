"""Tool factories for the bundled chat-artifact rendering plugin."""

from __future__ import annotations

from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext
from app.tools.artifact_agent import make_artifact_tool as build_artifact_tool


def make_artifact_tool(ctx: ToolContext) -> AgentTool:
    """Return the surface-aware ``render_artifact`` tool."""
    return build_artifact_tool(surface=ctx.surface)
