"""Agent-loop adapter for the LCM grep tool (PR #4).

Exposes :func:`make_lcm_grep_tool` which returns an :class:`AgentTool`
that the provider can append to ``AgentContext.tools``.  The actual DB
search lives in :mod:`app.tools.lcm_grep`; this module only handles
the JSON schema and the thin async wrapper the loop calls.

Usage::

    from app.tools.lcm_grep_agent import make_lcm_grep_tool

    if settings.lcm_enabled:
        tools.append(make_lcm_grep_tool(conversation_id=conv.id))
"""

from __future__ import annotations

import uuid
from typing import Any

from app.agents.types import AgentTool
from app.infrastructure.database.legacy import async_session_maker
from app.tools.display import make_tool_display, summarize_query
from app.tools.lcm_grep import _MAX_RESULTS_DEFAULT, lcm_grep

_TOOL_NAME = "lcm_grep"

_TOOL_DESCRIPTION = (
    "Search the full history of this conversation — including any compacted"
    " summaries — for a keyword or phrase.  Use this when you need to recall"
    " something that may have been mentioned earlier but is no longer in your"
    " current context window.  Returns matching excerpts from both raw messages"
    " and summary nodes, annotated with their position in the conversation."
    " Results are ordered most-recent-first.  Prefer short, distinctive search"
    " terms (1-3 words) for best recall."
)

_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Keyword or phrase to search for.  Case-insensitive substring"
                " match.  Use a short, distinctive term for best results."
            ),
        },
        "limit": {
            "type": "integer",
            "description": (
                f"Maximum number of matches per source (messages + summaries"
                f" searched independently).  Default {_MAX_RESULTS_DEFAULT}."
            ),
            "default": _MAX_RESULTS_DEFAULT,
            "minimum": 1,
            "maximum": 50,
        },
    },
    "required": ["query"],
}


def make_lcm_grep_tool(*, conversation_id: uuid.UUID) -> AgentTool:
    """Return an :class:`AgentTool` wrapping the LCM history search.

    The tool opens its own database session per call so it is independent
    of the request-scoped session.

    Args:
        conversation_id: The conversation to search.  Baked into the closure
            at tool construction time so the agent cannot search other
            conversations.

    Returns:
        A configured :class:`AgentTool` ready to be appended to the tools list.
    """

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        query = str(kwargs.get("query") or "")
        raw_limit = kwargs.get("limit")
        limit = int(raw_limit) if isinstance(raw_limit, int | float | str) else _MAX_RESULTS_DEFAULT
        limit = max(1, min(50, limit))
        async with async_session_maker() as session:
            return await lcm_grep(
                session,
                conversation_id=conversation_id,
                query=query,
                limit=limit,
            )

    return AgentTool(
        name=_TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        parameters=_PARAMETERS,
        execute=_execute,
        display=make_tool_display(
            icon="🧠",
            label="Search Chat History",
            present=lambda args: (
                f"🧠 Searching chat history for {summarize_query(args.get('query'))}"
            ),
            compact=lambda args: f"Search chat history -> {summarize_query(args.get('query'))}",
        ),
    )
