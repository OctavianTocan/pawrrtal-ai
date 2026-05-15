"""Agent-loop adapter for the Exa web-search tool.

Exposes :func:`make_exa_search_tool` which returns an :class:`AgentTool`
that the Gemini (and any future) provider can append to
``AgentContext.tools``.  The actual network call lives in the shared core
(:mod:`app.core.tools.exa_search`) — this module only handles the schema
definition and the thin async wrapper the loop calls.

Usage::

    from app.core.tools.exa_search_agent import make_exa_search_tool

    tools = [make_exa_search_tool(user_id=user.id)] if settings.exa_api_key else []
    context = AgentContext(system_prompt=..., messages=..., tools=tools)
"""

from __future__ import annotations

import uuid

from app.core.agent_loop.types import AgentTool
from app.core.keys import resolve_api_key
from app.core.tools.exa_search import (
    MAX_NUM_RESULTS,
    exa_search,
    format_results_as_markdown,
)

_TOOL_NAME = "exa_search"

_TOOL_DESCRIPTION = (
    "Search the public web through Exa and return up to "
    f"{MAX_NUM_RESULTS} ranked results with title, URL, publish date, "
    "and short relevance highlights. Use this whenever the user asks "
    "for fresh information, current events, citations, or anything "
    "that requires going beyond your training data. Always cite the "
    "result URLs when you use information from them."
)

# JSON Schema for the tool's parameters — the agent loop passes this to
# the LLM so it knows how to call the tool.
_PARAMETERS: dict = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Natural-language search query. Exa uses neural search, so "
                "longer, more descriptive queries typically yield better results "
                "than short keyword strings."
            ),
        },
        "num_results": {
            "type": "integer",
            "description": (
                f"Number of results to return (1-{MAX_NUM_RESULTS}). "
                "Default 5 keeps token usage low."
            ),
            "default": 5,
            "minimum": 1,
            "maximum": MAX_NUM_RESULTS,
        },
        "include_full_text": {
            "type": "boolean",
            "description": (
                "When true, include the full page text alongside highlights. "
                "Significantly increases token usage — prefer false unless "
                "deep reading of the source is required."
            ),
            "default": False,
        },
    },
    "required": ["query"],
}


def make_exa_search_tool(*, workspace_id: uuid.UUID | None = None) -> AgentTool:
    """Return an :class:`AgentTool` wrapping the Exa web-search core.

    Args:
        workspace_id: Active workspace UUID, used to resolve per-workspace
            API key overrides. When ``None`` the global settings key is used.

    Returns:
        A configured :class:`AgentTool` ready to be appended to
        ``AgentContext.tools``.
    """

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        """Call Exa and return formatted Markdown for the LLM."""
        query = str(kwargs.get("query") or "")
        num_results = int(kwargs.get("num_results") or 5)
        include_full_text = bool(kwargs.get("include_full_text") or False)
        api_key = None
        if workspace_id:
            api_key = resolve_api_key(workspace_id, "EXA_API_KEY")
        result = await exa_search(
            query,
            num_results=num_results,
            include_full_text=include_full_text,
            api_key=api_key,
        )
        return format_results_as_markdown(result)

    return AgentTool(
        name=_TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        parameters=_PARAMETERS,
        execute=_execute,
    )
