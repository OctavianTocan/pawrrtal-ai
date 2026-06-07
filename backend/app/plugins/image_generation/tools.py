"""Tool factories for the bundled image-generation plugin."""

from __future__ import annotations

from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext
from app.tools.image_gen_agent import make_image_gen_tool as build_image_gen_tool


def make_image_gen_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``generate_image`` tool."""
    return build_image_gen_tool(workspace_root=ctx.workspace_root)
