"""Tool factories for the bundled Exa web-search plugin."""

from __future__ import annotations

from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext
from app.tools.exa_search_agent import make_exa_search_tool as build_exa_search_tool


def make_exa_search_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``exa_search`` tool."""
    return build_exa_search_tool(workspace_root=ctx.workspace_root)
