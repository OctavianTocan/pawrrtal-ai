"""Tests for the Claude-side cross-provider tool bridge.

Covers :mod:`app.providers._claude_tool_bridge` and its wiring
into :class:`app.providers.claude_provider.ClaudeLLM`.

The bridge translates the provider-neutral
:class:`app.agents.types.AgentTool` shape into Claude's
in-process MCP server format (``create_sdk_mcp_server`` + the
``mcp__<server>__<tool>`` allowed-tools whitelist).  These tests
verify:

  * The bridge composes the canonical tool ID correctly.
  * An empty AgentTool list produces no MCP server (vs an empty one).
  * Wrapping an AgentTool preserves its ``execute`` semantics and
    surfaces the result as the SDK's text-content shape.
  * ``ClaudeLLM._build_options`` mounts the server + appends the
    whitelist when handed AgentTools.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.agents.types import AgentTool
from app.providers.claude import ClaudeLLM, ClaudeLLMConfig
from app.providers.claude import tool_bridge as bridge
from app.providers.claude.tool_bridge import (
    MCP_SERVER_NAME,
    allowed_tool_ids,
    build_mcp_server,
    claude_tool_id,
)


def _make_agent_tool(name: str = "echo") -> AgentTool:
    async def _execute(_call_id: str, **kwargs: Any) -> str:
        return f"echoed:{kwargs.get('text', '')}"

    return AgentTool(
        name=name,
        description=f"echo back the {name!r} parameter",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        execute=_execute,
    )


def test_claude_tool_id_composes_canonical_mcp_identifier() -> None:
    assert claude_tool_id("read_file") == f"mcp__{MCP_SERVER_NAME}__read_file"


def test_allowed_tool_ids_returns_one_entry_per_agent_tool() -> None:
    tools = [_make_agent_tool("a"), _make_agent_tool("b")]
    assert allowed_tool_ids(tools) == [
        f"mcp__{MCP_SERVER_NAME}__a",
        f"mcp__{MCP_SERVER_NAME}__b",
    ]


def test_build_mcp_server_returns_none_for_empty_list() -> None:
    """No tools → no server.

    Mounting an empty server is harmless but pointlessly noisy in
    SDK logs and would mislead readers into thinking tools were
    enabled.  The provider should branch on ``None``.
    """
    assert build_mcp_server([]) is None


def test_build_mcp_server_returns_named_sdk_config_for_one_tool() -> None:
    config = build_mcp_server([_make_agent_tool("echo")])
    # ``McpSdkServerConfig`` is a TypedDict-shaped mapping the SDK
    # accepts; verify the surface our provider depends on rather
    # than coupling to internal SDK types.
    assert isinstance(config, dict)
    assert config.get("type") == "sdk"
    assert config.get("name") == MCP_SERVER_NAME


@pytest.mark.anyio
async def test_wrapped_tool_returns_text_content_on_success() -> None:
    """The bridge must surface the AgentTool result as a Claude text block."""
    sdk_tool = bridge._wrap(_make_agent_tool("echo"))
    result = await sdk_tool.handler({"text": "hi"})

    assert result["is_error"] is False
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "echoed:hi"


@pytest.mark.anyio
async def test_wrapped_tool_marks_is_error_when_execute_raises() -> None:
    async def _explode(_call_id: str, **_kwargs: Any) -> str:
        raise RuntimeError("boom")

    failing = AgentTool(
        name="boom",
        description="always fails",
        parameters={"type": "object", "properties": {}},
        execute=_explode,
    )

    sdk_tool = bridge._wrap(failing)
    result = await sdk_tool.handler({})

    assert result["is_error"] is True
    assert "boom" in result["content"][0]["text"]


@pytest.mark.anyio
async def test_wrapped_tool_blocks_confirmation_required_tool() -> None:
    executed = False

    async def _execute(_call_id: str, **_kwargs: Any) -> str:
        nonlocal executed
        executed = True
        return "leaked"

    tool = AgentTool(
        name="python",
        description="run trusted Python code",
        parameters={"type": "object", "properties": {"code": {"type": "string"}}},
        execute=_execute,
        requires_confirmation=True,
    )

    sdk_tool = bridge._wrap(tool)
    result = await sdk_tool.handler({"code": "print('hi')"})

    assert executed is False
    assert result["is_error"] is True
    assert result["content"][0]["text"].startswith("[permission_denied]")
    assert "requires confirmation" in result["content"][0]["text"]


def test_provider_options_mount_server_and_whitelist_for_agent_tools() -> None:
    """``ClaudeLLM._build_options`` must propagate AgentTools to the SDK."""
    provider = ClaudeLLM(
        "claude-haiku-4-5",
        config=ClaudeLLMConfig(oauth_token=None),
    )

    options = provider._build_options(uuid4(), agent_tools=[_make_agent_tool("read_file")])

    assert isinstance(options.mcp_servers, dict)
    assert MCP_SERVER_NAME in options.mcp_servers

    tools = options.tools or []
    assert claude_tool_id("read_file") in tools


def test_provider_options_omit_server_when_no_agent_tools_supplied() -> None:
    provider = ClaudeLLM(
        "claude-haiku-4-5",
        config=ClaudeLLMConfig(oauth_token=None),
    )

    options = provider._build_options(uuid4(), agent_tools=None)

    # No agent tools → no server, no whitelist additions.
    assert options.mcp_servers == {} or options.mcp_servers is None
    # Whatever the config-level local tools whitelist was should pass
    # through unchanged — the bridge never silently strips it.
    assert options.tools == list(provider._config.tools or [])
