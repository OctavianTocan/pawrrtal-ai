"""Tool factory for the bundled Python shell plugin."""

from __future__ import annotations

from app.agents.types import AgentTool
from app.infrastructure.config import settings
from app.plugins.tool_context import ToolContext
from app.tools.python_exec import make_virtual_python_tool


def make_python_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``python`` execution tool."""
    return make_virtual_python_tool(
        workspace_root=ctx.workspace_root,
        timeout_seconds=settings.virtual_python_timeout_seconds,
        output_cap_bytes=settings.virtual_python_output_cap_bytes,
    )
