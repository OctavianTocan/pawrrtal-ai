"""Tool factories for the bundled task-management plugin."""

from __future__ import annotations

from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext
from app.tools.tasks_md import (
    make_add_task_tool as build_add_task_tool,
)
from app.tools.tasks_md import (
    make_complete_task_tool as build_complete_task_tool,
)
from app.tools.tasks_md import (
    make_list_tasks_tool as build_list_tasks_tool,
)


def make_add_task_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``add_task`` tool."""
    return build_add_task_tool(workspace_root=ctx.workspace_root)


def make_list_tasks_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``list_tasks`` tool."""
    return build_list_tasks_tool(workspace_root=ctx.workspace_root)


def make_complete_task_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``complete_task`` tool."""
    return build_complete_task_tool(workspace_root=ctx.workspace_root)
