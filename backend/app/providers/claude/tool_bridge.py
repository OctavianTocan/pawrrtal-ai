"""Claude Agent SDK bridge for the cross-provider :class:`AgentTool` shape.

The agent loop hands every provider a ``list[AgentTool]`` (see
``app.agents.types``) — a provider-neutral dataclass with
``name``, ``description``, JSON-Schema ``parameters`` and an async
``execute(tool_call_id, **kwargs) -> str``.  The Gemini provider
translates that list into ``gtypes.FunctionDeclaration``; this module
is the equivalent translation for Claude.

Claude exposes custom tools via *in-process* MCP servers built with
``create_sdk_mcp_server`` (despite the "MCP" label there is no IPC,
no extra process — it's just the SDK's calling convention for
caller-supplied tools, per the official docstring).  We wrap each
:class:`AgentTool` with the SDK's ``@tool`` decorator and assemble
them into a single server named :data:`MCP_SERVER_NAME`, which the
provider mounts via ``ClaudeAgentOptions.mcp_servers``.

The bridge is intentionally a ``providers/_*`` private module rather
than an ``app.tools.*`` import: the no-tools-in-providers gate
(``scripts/check-no-tools-in-providers.py``) blocks providers from
reaching into specific tool factories, but provider-internal plumbing
that translates the *abstract* ``AgentTool`` is exactly what we want
to live next to the provider.

The SDK-side ``can_use_tool`` callback (:func:`auto_approve_bridge_tools`)
auto-approves every call inside our ``mcp__pawrrtal__*`` namespace.  The
SDK requires *some* ``can_use_tool`` hook once a custom MCP server is
mounted; this is the closest-to-auto-approve value that still refuses
tools from an unexpected MCP server (defence in depth) without resorting
to ``permission_mode='bypassPermissions'`` (which would auto-approve
*every* tool the SDK exposes, not just ours).
"""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import (
    PermissionResultAllow,
    PermissionResultDeny,
    create_sdk_mcp_server,
    tool,
)
from claude_agent_sdk.types import ToolPermissionContext

from app.agents.types import AgentTool

logger = logging.getLogger(__name__)

# The single in-process MCP server name we mount every cross-provider
# AgentTool under.  Claude addresses each tool as
# ``mcp__<server>__<tool_name>``; both the server name and that prefix
# are stable so the allowed-tools whitelist is computable from the
# AgentTool list alone.
MCP_SERVER_NAME = "pawrrtal"


def claude_tool_id(name: str) -> str:
    """Return the canonical Claude tool ID for an :class:`AgentTool` ``name``.

    Useful when whitelisting the tool in
    ``ClaudeAgentOptions.tools`` — the SDK refuses execution otherwise.
    """
    return f"mcp__{MCP_SERVER_NAME}__{name}"


def _wrap(agent_tool: AgentTool) -> Any:
    """Wrap one :class:`AgentTool` in a Claude SDK ``@tool``.

    Returns the decorated handler so :func:`build_mcp_server` can pass
    it straight to ``create_sdk_mcp_server(tools=[...])``.

    Why a closure rather than a class with ``__call__``: the SDK's
    ``@tool`` decorator inspects the wrapped function and stores
    metadata on the returned ``SdkMcpTool`` — wrapping a fresh closure
    per agent_tool keeps that metadata tidy and avoids state sharing.
    """

    @tool(agent_tool.name, agent_tool.description, agent_tool.parameters)
    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            text = await agent_tool.execute("", **args)
        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"Tool error: {exc}"}],
                "is_error": True,
            }
        return {
            "content": [{"type": "text", "text": text}],
            "is_error": False,
        }

    return _handler


def build_mcp_server(agent_tools: list[AgentTool]) -> Any | None:
    """Return an in-process MCP server config exposing every *agent_tool*.

    Args:
        agent_tools: The provider-neutral tool list the agent loop
            hands the provider.  May be empty.

    Returns:
        A ``McpSdkServerConfig`` ready to mount under
        ``ClaudeAgentOptions.mcp_servers[MCP_SERVER_NAME]``, or
        ``None`` when the list is empty (the provider should then omit
        the ``mcp_servers`` kwarg entirely — passing an empty dict is
        accepted by the SDK but pointlessly noisy in logs).
    """
    if not agent_tools:
        return None
    return create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        version="1.0.0",
        tools=[_wrap(t) for t in agent_tools],
    )


def allowed_tool_ids(agent_tools: list[AgentTool]) -> list[str]:
    """Return the Claude allowed-tools whitelist for *agent_tools*.

    Each entry is ``mcp__<MCP_SERVER_NAME>__<tool.name>``; the SDK
    requires the whitelist or it refuses execution even when the
    server is mounted.
    """
    return [claude_tool_id(t.name) for t in agent_tools]


_NAMESPACE_PREFIX = f"mcp__{MCP_SERVER_NAME}__"


def _allow(_input: dict[str, Any]) -> PermissionResultAllow:
    """Build a Claude SDK ``Allow`` carrying the unmodified input back."""
    return PermissionResultAllow(
        behavior="allow",
        updated_input=_input,
        updated_permissions=None,
    )


def _deny(message: str) -> PermissionResultDeny:
    """Build a Claude SDK ``Deny`` with a human-readable reason."""
    return PermissionResultDeny(
        behavior="deny",
        message=message,
        interrupt=False,
    )


async def auto_approve_bridge_tools(
    tool_name: str,
    _input: dict[str, Any],
    _ctx: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    """``can_use_tool`` callback: auto-approve our bridged AgentTools.

    Without this hook the SDK enforces interactive permission grants on
    every custom MCP tool call — the integration test on PR #131
    surfaced this with::

        Claude requested permissions to use mcp__pawrrtal__echo_back,
        but you haven't granted it yet.

    The ``allowed_tools`` whitelist is necessary but not sufficient:
    it tells the SDK these tools are *known*, not that they're
    *pre-approved*.  Returning ``Allow`` for our
    ``mcp__<MCP_SERVER_NAME>__*`` namespace closes the gap without
    resorting to ``permission_mode='bypassPermissions'`` (which
    would silently auto-approve every tool the SDK exposes, not
    just ours).

    Tools outside our namespace get an explicit ``deny`` so a future
    misconfiguration that mounts an unexpected MCP server can't
    silently piggy-back on this approval.
    """
    if tool_name.startswith(_NAMESPACE_PREFIX):
        return _allow(_input)
    return _deny(
        f"Tool {tool_name!r} is outside the bridge's namespace ({MCP_SERVER_NAME!r}); deny."
    )
