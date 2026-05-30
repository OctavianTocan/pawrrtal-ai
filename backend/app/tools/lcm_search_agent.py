"""Agent-loop adapter for the ranked LCM search tool (issue #253).

Mirrors the lcm_grep adapter shape so the chat router can wire both
tools the same way.  The backing search lives in
:mod:`app.tools.lcm_search`; this module only owns the JSON
schema and the thin async wrapper the agent loop calls.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.agents.types import AgentTool
from app.infrastructure.database.legacy import async_session_maker
from app.tools.lcm_search import (
    _DEFAULT_LIMIT,
    _MAX_LIMIT,
    format_results,
    lcm_search,
)

_TOOL_NAME = "lcm_search"

_TOOL_DESCRIPTION = (
    "Run ranked lexical search over this conversation's full history,"
    " including compacted summaries.  Returns scored excerpts with"
    " item kind (message vs summary), ordinal/role for raw messages,"
    " summary depth/kind for summary nodes, and a stable score so"
    " callers can rank further.  Use this when lcm_grep's substring"
    " match would miss relevant context because the user's wording"
    " does not match the original phrasing exactly.  Results are"
    " ordered by score descending."
)

_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Question or keyword phrase.  The scorer tokenises this,"
                " drops stopwords + tokens shorter than 3 characters,"
                " then ranks candidates by term frequency, multi-token"
                " coverage, and length-normalisation."
            ),
        },
        "limit": {
            "type": "integer",
            "description": (
                f"Maximum number of ranked results to return."
                f"  Defaults to {_DEFAULT_LIMIT}, capped at {_MAX_LIMIT}."
            ),
            "default": _DEFAULT_LIMIT,
            "minimum": 1,
            "maximum": _MAX_LIMIT,
        },
        "include_messages": {
            "type": "boolean",
            "description": "Include raw chat messages in the ranked set.",
            "default": True,
        },
        "include_summaries": {
            "type": "boolean",
            "description": "Include LCM summary nodes in the ranked set.",
            "default": True,
        },
    },
    "required": ["query"],
}


def make_lcm_search_tool(*, conversation_id: uuid.UUID) -> AgentTool:
    """Return an :class:`AgentTool` wrapping the ranked LCM search.

    The tool opens its own database session per call so it is
    independent of the request-scoped session.  ``conversation_id``
    is baked into the closure at construction so the agent cannot
    search across other users' conversations.
    """

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        query = str(kwargs.get("query") or "")
        limit_raw = kwargs.get("limit")
        try:
            limit_val: int | None = int(limit_raw) if limit_raw is not None else None  # type: ignore[call-overload]
        except (TypeError, ValueError):
            limit_val = None
        include_messages = bool(kwargs.get("include_messages", True))
        include_summaries = bool(kwargs.get("include_summaries", True))

        async with async_session_maker() as session:
            results = await lcm_search(
                session,
                conversation_id=conversation_id,
                query=query,
                limit=limit_val,
                include_messages=include_messages,
                include_summaries=include_summaries,
            )
        return format_results(query, results)

    return AgentTool(
        name=_TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        parameters=_PARAMETERS,
        execute=_execute,
    )
