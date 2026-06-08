"""Tool factories for the bundled reminder scheduling plugin."""

from __future__ import annotations

from app.agents.tool_capabilities.core import (
    make_reminder_cancel_tool as build_reminder_cancel_tool,
)
from app.agents.tool_capabilities.core import (
    make_reminder_list_tool as build_reminder_list_tool,
)
from app.agents.tool_capabilities.core import (
    make_reminder_schedule_tool as build_reminder_schedule_tool,
)
from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext


def make_reminder_schedule_tool(ctx: ToolContext) -> AgentTool:
    """Return the user-bound ``reminder_schedule`` tool."""
    return build_reminder_schedule_tool(
        user_id=ctx.user_id,
        conversation_id=ctx.conversation_id,
    )


def make_reminder_list_tool(ctx: ToolContext) -> AgentTool:
    """Return the user-bound ``reminder_list`` tool."""
    return build_reminder_list_tool(user_id=ctx.user_id)


def make_reminder_cancel_tool(ctx: ToolContext) -> AgentTool:
    """Return the user-bound ``reminder_cancel`` tool."""
    return build_reminder_cancel_tool(user_id=ctx.user_id)
