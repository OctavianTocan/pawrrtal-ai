"""Tool factories for the bundled skill-discovery plugin."""

from __future__ import annotations

from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext
from app.tools.skill_invocation import (
    make_invoke_skill_tool as build_invoke_skill_tool,
)
from app.tools.skill_invocation import (
    make_list_skills_tool as build_list_skills_tool,
)
from app.tools.skill_invocation import (
    make_read_skill_tool as build_read_skill_tool,
)


def make_list_skills_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``list_skills`` tool."""
    return build_list_skills_tool(workspace_root=ctx.workspace_root)


def make_read_skill_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``read_skill`` tool."""
    return build_read_skill_tool(workspace_root=ctx.workspace_root)


def make_invoke_skill_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``invoke_skill`` tool."""
    return build_invoke_skill_tool(workspace_root=ctx.workspace_root)
