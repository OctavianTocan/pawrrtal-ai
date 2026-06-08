"""Tool factories for the bundled document-conversion plugin."""

from __future__ import annotations

from app.agents.tool_capabilities.core import make_markitdown_tool as build_markitdown_tool
from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext


def make_markitdown_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``convert_to_markdown`` tool."""
    return build_markitdown_tool(workspace_root=ctx.workspace_root)
