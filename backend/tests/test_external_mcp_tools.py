"""Tests for the external MCP server bridge (#317)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.core.tools.external_mcp import (
    _bounded,
    _sanitize,
    build_external_mcp_tools,
)

pytestmark = pytest.mark.anyio


def test_sanitize_replaces_non_alnum_with_underscores() -> None:
    assert _sanitize("notion-search") == "notion_search"
    assert _sanitize("my server!") == "my_server"
    assert _sanitize("") == "tool"


def test_bounded_returns_text_unchanged_when_under_cap() -> None:
    assert _bounded("hello") == "hello"


def test_bounded_truncates_with_marker_when_over_cap() -> None:
    huge = "x" * 100_000
    result = _bounded(huge)
    assert result.endswith("…[truncated]")
    assert len(result.encode("utf-8")) < 50_000


def test_build_external_mcp_tools_drops_unsupported_transports() -> None:
    configs = [
        {"name": "stdio-server", "config": {"transport": "stdio", "command": "ls"}},
    ]
    tools = build_external_mcp_tools(configs)
    assert tools == []


def test_build_external_mcp_tools_drops_servers_without_url() -> None:
    configs = [
        {"name": "broken", "config": {"transport": "http"}},
    ]
    tools = build_external_mcp_tools(configs)
    assert tools == []


def test_build_external_mcp_tools_drops_servers_with_no_name() -> None:
    configs: list[dict[str, Any]] = [{"name": "", "config": {"transport": "http"}}]
    tools = build_external_mcp_tools(configs)
    assert tools == []


def test_build_external_mcp_tools_wraps_each_discovered_tool() -> None:
    with patch("app.core.tools.external_mcp._list_tools_sync") as mock_list:
        mock_list.return_value = [
            {
                "name": "search",
                "description": "Search Notion.",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
            {
                "name": "get_page",
                "description": "Read a page.",
                "input_schema": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                },
            },
        ]
        tools = build_external_mcp_tools(
            [{"name": "notion", "config": {"transport": "http", "url": "https://x"}}]
        )
    names = sorted(t.name for t in tools)
    assert names == ["mcp_notion_get_page", "mcp_notion_search"]


def test_build_external_mcp_tools_caps_per_server() -> None:
    huge = [{"name": f"tool_{i}", "description": "", "input_schema": {}} for i in range(200)]
    with patch("app.core.tools.external_mcp._list_tools_sync", return_value=huge):
        tools = build_external_mcp_tools(
            [{"name": "noisy", "config": {"transport": "http", "url": "https://x"}}]
        )
    # _MAX_TOOLS_PER_SERVER = 64
    assert len(tools) == 64


async def test_execute_proxies_to_call_tool_endpoint() -> None:
    with patch("app.core.tools.external_mcp._list_tools_sync") as mock_list:
        mock_list.return_value = [
            {
                "name": "search",
                "description": "Search.",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }
        ]
        tools = build_external_mcp_tools(
            [{"name": "notion", "config": {"transport": "http", "url": "https://x"}}]
        )
    tool = tools[0]

    async def fake_call(
        *, url: str, headers: dict[str, Any], tool_name: str, arguments: dict[str, Any]
    ) -> str:
        assert url == "https://x"
        assert tool_name == "search"
        assert arguments == {"query": "hi"}
        return "result"

    with patch("app.core.tools.external_mcp._call_remote_tool", side_effect=fake_call):
        out = await tool.execute("call-1", query="hi")
    assert out == "result"


async def test_execute_returns_io_error_on_http_failure() -> None:
    with patch("app.core.tools.external_mcp._list_tools_sync") as mock_list:
        mock_list.return_value = [
            {"name": "search", "description": "", "input_schema": {}},
        ]
        tools = build_external_mcp_tools(
            [{"name": "notion", "config": {"transport": "http", "url": "https://x"}}]
        )
    tool = tools[0]

    async def boom(**_kwargs: Any) -> str:
        raise httpx.ConnectError("connection refused")

    with patch("app.core.tools.external_mcp._call_remote_tool", side_effect=boom):
        out = await tool.execute("call-1")
    assert "IO_ERROR" in out or "connection refused" in out
