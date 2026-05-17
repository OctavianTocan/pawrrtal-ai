"""Agent-loop adapter for the LCM describe tool (PR #5).

Exposes two :class:`AgentTool` factories:

* :func:`make_lcm_describe_tool` — inspect a specific summary by ID.
* :func:`make_lcm_list_summaries_tool` — enumerate all summaries for
  the current conversation (so the agent can find the right ID to pass
  to ``lcm_describe``).

Usage::

    from app.core.tools.lcm_describe_agent import (
        make_lcm_describe_tool,
        make_lcm_list_summaries_tool,
    )

    if settings.lcm_enabled:
        tools.append(make_lcm_list_summaries_tool(conversation_id=conv.id))
        tools.append(make_lcm_describe_tool(conversation_id=conv.id))
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.tools.display import make_tool_display
from app.core.tools.lcm_describe import lcm_describe, lcm_list_summaries
from app.db import async_session_maker

# ---------------------------------------------------------------------------
# lcm_list_summaries
# ---------------------------------------------------------------------------

_LIST_TOOL_NAME = "lcm_list_summaries"

_LIST_TOOL_DESCRIPTION = (
    "List all compacted summary nodes for the current conversation, most-recent-first."
    "  Each entry shows the summary ID, depth, kind, token count, and a brief excerpt."
    "  Use this to discover which summary IDs are available before calling"
    " ``lcm_describe`` to read one in full."
)

_LIST_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
}


def make_lcm_list_summaries_tool(*, conversation_id: uuid.UUID) -> AgentTool:
    """Return an :class:`AgentTool` that lists LCM summary nodes for a conversation.

    Args:
        conversation_id: Baked into the closure — the agent cannot list
            summaries from other conversations.
    """

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        async with async_session_maker() as session:
            return await lcm_list_summaries(session, conversation_id=conversation_id)

    return AgentTool(
        name=_LIST_TOOL_NAME,
        description=_LIST_TOOL_DESCRIPTION,
        parameters=_LIST_PARAMETERS,
        execute=_execute,
        display=make_tool_display(
            icon="🧠",
            label="List memory summaries",
            present=lambda _args: "🧠 Listing memory summaries",
            compact=lambda _args: "List memory summaries",
        ),
    )


# ---------------------------------------------------------------------------
# lcm_describe
# ---------------------------------------------------------------------------

_DESCRIBE_TOOL_NAME = "lcm_describe"

_DESCRIBE_TOOL_DESCRIPTION = (
    "Read the full content and metadata of a single compacted summary node."
    "  Supply the summary ID (obtained via ``lcm_list_summaries`` or from a"
    " ``[SUMMARY`` annotation in ``lcm_grep`` output)."
    "  Returns the complete summary text and its source-edge list."
    "  This is a cheap single-row lookup — use it freely to recover compacted"
    " context without the overhead of a full expand_query sub-agent."
)

_DESCRIBE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary_id": {
            "type": "string",
            "description": (
                "UUID of the LCMSummary node to inspect."
                " Obtain this from lcm_list_summaries or from a [SUMMARY ..."
                " annotation in lcm_grep output."
            ),
        },
    },
    "required": ["summary_id"],
}


def make_lcm_describe_tool(*, conversation_id: uuid.UUID) -> AgentTool:
    """Return an :class:`AgentTool` that reads a specific LCMSummary in full.

    Args:
        conversation_id: Baked into the closure — prevents cross-conversation
            inspection even if the agent passes a foreign UUID.
    """

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        raw_id = str(kwargs.get("summary_id") or "")
        try:
            sid = uuid.UUID(raw_id)
        except ValueError:
            return f"lcm_describe: invalid UUID {raw_id!r}"

        async with async_session_maker() as session:
            return await lcm_describe(
                session,
                conversation_id=conversation_id,
                summary_id=sid,
            )

    return AgentTool(
        name=_DESCRIBE_TOOL_NAME,
        description=_DESCRIBE_TOOL_DESCRIPTION,
        parameters=_DESCRIBE_PARAMETERS,
        execute=_execute,
        display=make_tool_display(
            icon="🧠",
            label="Read memory summary",
            present=lambda _args: "🧠 Reading memory summary",
            compact=lambda _args: "Read memory summary",
        ),
    )
