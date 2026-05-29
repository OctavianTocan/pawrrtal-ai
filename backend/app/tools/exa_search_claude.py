"""Claude Agent SDK adapter for the Exa web-search tool.

Exposes :func:`build_exa_mcp_server` which returns an in-process MCP
server config the Claude provider can pass to ``ClaudeAgentOptions.mcp_servers``.
The server registers a single tool, ``exa_search``, that delegates to the
shared core in :mod:`app.tools.exa_search`.

The MCP server name (:data:`MCP_SERVER_NAME`) is intentionally a constant
so the provider can compute the canonical Claude tool identifier
(``mcp__<server>__<tool>``) and add it to ``allowed_tools``.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from .exa_search import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
    exa_search,
    format_results_as_markdown,
)

# Identifier used by Claude when invoking the tool: mcp__<server>__<tool>.
MCP_SERVER_NAME = "pawrrtal"
MCP_TOOL_NAME = "exa_search"

# Public allowed_tools entry. Whitelist this string in ClaudeAgentOptions
# so the SDK actually permits the tool — without it the model knows the
# tool exists but the SDK refuses execution.
CLAUDE_TOOL_ID = f"mcp__{MCP_SERVER_NAME}__{MCP_TOOL_NAME}"

_TOOL_DESCRIPTION = (
    "Search the public web through Exa and return up to "
    f"{MAX_NUM_RESULTS} ranked results with title, URL, publish date, "
    "and short relevance highlights. Use this whenever the user asks "
    "for fresh information, current events, citations, or anything "
    "that requires going beyond your training data. Always cite the "
    "URLs returned by this tool when you use the results."
)

_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Natural-language search query. Prefer rich, descriptive "
                "phrasing — Exa is a neural search engine, not keyword."
            ),
        },
        "num_results": {
            "type": "integer",
            "description": (
                "Number of results to return. Default "
                f"{DEFAULT_NUM_RESULTS}; max {MAX_NUM_RESULTS}."
            ),
            "minimum": 1,
            "maximum": MAX_NUM_RESULTS,
        },
    },
    "required": ["query"],
}


@tool(MCP_TOOL_NAME, _TOOL_DESCRIPTION, _INPUT_SCHEMA)
async def _exa_search_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Claude SDK ``@tool`` handler — formats the result as Markdown text.

    Returning Markdown in a single ``text`` content block lines up with
    how Claude already renders tool outputs in the chat surface (the
    frontend's :file:`ChainOfThought.tsx` uses ``ToolResultBlock`` text
    directly), so we don't need any custom rendering on top.
    """
    query = str(args.get("query") or "").strip()
    if not query:
        return {
            "content": [{"type": "text", "text": "Web search requires a non-empty query."}],
            "is_error": True,
        }

    requested = args.get("num_results")
    num_results = int(requested) if isinstance(requested, (int, float)) else DEFAULT_NUM_RESULTS

    result = await exa_search(query, num_results=num_results)
    text = format_results_as_markdown(result)
    return {
        "content": [{"type": "text", "text": text}],
        "is_error": result["error"] is not None,
    }


def build_exa_mcp_server() -> Any:
    """Return an in-process MCP server config exposing the Exa tool.

    Returns:
        ``McpSdkServerConfig`` ready to slot into
        ``ClaudeAgentOptions.mcp_servers={MCP_SERVER_NAME: ...}``.
    """
    return create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        version="1.0.0",
        tools=[_exa_search_tool],
    )
