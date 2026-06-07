"""Tool factories for the bundled document-conversion plugin."""

from __future__ import annotations

from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext
from app.tools.markitdown_convert import make_markitdown_tool as build_markitdown_tool


def make_markitdown_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``convert_to_markdown`` tool."""
    return build_markitdown_tool(workspace_root=ctx.workspace_root)
