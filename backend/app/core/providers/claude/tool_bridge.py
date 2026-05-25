"""Claude Agent SDK bridge for the cross-provider :class:`AgentTool` shape.

The agent loop hands every provider a ``list[AgentTool]`` (see
``app.core.agent_loop.types``) — a provider-neutral dataclass with
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
than an ``app.core.tools.*`` import: the no-tools-in-providers gate
(``scripts/check-no-tools-in-providers.py``) blocks providers from
reaching into specific tool factories, but provider-internal plumbing
that translates the *abstract* ``AgentTool`` is exactly what we want
to live next to the provider.

PR 03b: ``make_can_use_tool`` extends the bridge so the SDK-side
``can_use_tool`` callback can also delegate to the cross-provider
:class:`PermissionCheckFn` — keeping Claude and Gemini policy in
lock-step.  When no ``PermissionCheckFn`` is supplied the historical
"namespace-only auto-approve" behaviour is preserved, so existing
callers keep working unchanged.
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

from app.core.agent_loop.types import AgentTool, PermissionCheckFn

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


def _strip_namespace(tool_name: str) -> str:
    """Return the bare AgentTool name from a Claude SDK tool ID.

    The cross-provider :class:`PermissionCheckFn` works in terms of
    the unprefixed names every tool factory registers (``Bash``,
    ``workspace_read``, …); the Claude SDK addresses our bridged
    tools as ``mcp__pawrrtal__<name>``.  Strip the namespace before
    delegating so policy authors don't have to know about Claude's
    addressing scheme.
    """
    if tool_name.startswith(_NAMESPACE_PREFIX):
        return tool_name[len(_NAMESPACE_PREFIX) :]
    return tool_name


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

    Default callback used when no cross-provider ``PermissionCheckFn``
    is supplied.  Without this hook the SDK enforces interactive
    permission grants on every custom MCP tool call — the integration
    test on PR #131 surfaced this with::

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


def make_can_use_tool(
    permission_check: PermissionCheckFn | None,
) -> Any:
    """Build the Claude SDK ``can_use_tool`` callback for one request.

    When ``permission_check`` is ``None`` we return
    :func:`auto_approve_bridge_tools` directly so existing callers
    keep working — historical behaviour is namespace-only approval,
    no per-call policy.

    When a :class:`PermissionCheckFn` is supplied (PR 03b chat-router
    wire-up), the returned callback:

    1. Rejects anything outside the ``mcp__pawrrtal__*`` namespace
       with the same message the legacy default uses.  Defence in
       depth — even if the gate is misconfigured, an unexpected MCP
       server can't piggy-back on our approval.
    2. Strips the ``mcp__pawrrtal__`` prefix from the tool name so
       the cross-provider gate sees the bare ``AgentTool.name`` it
       was authored against.
    3. Awaits the gate.  An ``Allow`` decision becomes a Claude SDK
       ``PermissionResultAllow``; a ``Deny`` becomes a
       ``PermissionResultDeny`` carrying the gate's reason verbatim
       so the model gets a useful error to react to.
    4. Treats a crashing gate as a closed fail (deny) so a buggy
       policy can't silently allow tool use.  Logged at WARNING so
       the operator notices.
    """
    if permission_check is None:
        return auto_approve_bridge_tools

    async def _delegated_can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        _ctx: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        if not tool_name.startswith(_NAMESPACE_PREFIX):
            return _deny(
                f"Tool {tool_name!r} is outside the bridge's namespace ({MCP_SERVER_NAME!r}); deny."
            )
        bare_name = _strip_namespace(tool_name)
        try:
            decision = await permission_check(bare_name, tool_input)
        except Exception as exc:
            # Failing closed: a crashed gate is a config bug, not a
            # permission signal.  Better to deny + log than to let
            # tool use slip through.
            logger.exception(
                "claude_tool_bridge: permission_check crashed; failing closed for %s",
                bare_name,
            )
            return _deny(f"Tool {bare_name!r} denied: permission check error ({exc}).")
        if decision.get("allow", False):
            return _allow(tool_input)
        reason = decision.get("reason") or "Tool call denied by permission policy."
        return _deny(reason)

    return _delegated_can_use_tool
