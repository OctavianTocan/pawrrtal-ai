"""Tool factories for the bundled GitHub issue-reporting plugin."""

from __future__ import annotations

from app.agents.tool_capabilities.core import make_report_issue_tool as build_report_issue_tool
from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext


def make_report_issue_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``report_issue`` tool."""
    return build_report_issue_tool(workspace_root=ctx.workspace_root)
