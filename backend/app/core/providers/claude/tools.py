"""Per-request whitelist + display-map composition for the Claude bridge.

Pulled out of :mod:`app.core.providers.claude.provider` so that file
stays under the 500-line budget; both helpers are also unit-tested
directly via ``test_claude_provider.py``.
"""

from __future__ import annotations

from typing import Any

from app.core.agent_loop.display import ToolDisplay, tool_display_map
from app.core.agent_loop.types import AgentTool
from app.core.providers.claude.tool_bridge import (
    MCP_SERVER_NAME as AGENT_TOOL_MCP_SERVER_NAME,
)
from app.core.providers.claude.tool_bridge import (
    allowed_tool_ids,
    build_mcp_server,
    claude_tool_id,
)


def _merge_agent_tools_into_whitelist(
    local_tools: list[str] | None,
    agent_tool_list: list[AgentTool],
    mcp_servers: dict[str, Any],
) -> list[str] | None:
    """Mount *agent_tool_list* as an MCP server and append its IDs to *local_tools*.

    Mutates *mcp_servers* in place (adding the bridge server when there
    is at least one tool) and returns the updated *local_tools* whitelist.
    Extracted from :meth:`ClaudeLLM._build_options` so the body stays under
    the project nesting budget.
    """
    if not agent_tool_list:
        return local_tools
    server = build_mcp_server(agent_tool_list)
    if server is not None:
        mcp_servers[AGENT_TOOL_MCP_SERVER_NAME] = server
    allowed = allowed_tool_ids(agent_tool_list)
    if local_tools is None:
        return list(allowed)
    deduped = list(local_tools)
    for tid in allowed:
        if tid not in deduped:
            deduped.append(tid)
    return deduped


def _claude_display_map(agent_tools: list[AgentTool]) -> dict[str, ToolDisplay]:
    """Return display metadata keyed by bare and Claude MCP-prefixed names."""
    bare = tool_display_map(agent_tools)
    mapped: dict[str, ToolDisplay] = dict(bare)
    for name, display in bare.items():
        mapped[claude_tool_id(name)] = display
    return mapped
