"""Bridge external MCP servers into the cross-provider :class:`AgentTool` shape (#317).

Each row in ``mcp_servers`` (one per user, see
:mod:`app.models`) carries an opaque ``config_json`` blob. This module
understands the HTTP transport shape:

    {"transport": "http", "url": "...", "headers": {"Authorization": "Bearer ..."}}

It walks each enabled row, fetches the tool inventory from the
remote server (``POST <url>/list_tools``), and returns one
:class:`AgentTool` per discovered tool. Calls are proxied through
``POST <url>/call_tool`` with the tool name + arguments. Discovery is
best-effort: a server that fails the handshake is logged + skipped so
one misbehaving config never breaks the chat router.

Schema assumption
~~~~~~~~~~~~~~~~~

The default reader speaks an HTTP wire shape modeled after the
``streamable-http`` flavour of the MCP spec:

    POST  /list_tools           -> {"tools": [{"name", "description", "input_schema"}]}
    POST  /call_tool            -> {"content": str}    or   {"is_error": true, "content": str}

Servers using the JSON-RPC dialect can be added with a separate
client; the abstraction here is the resulting ``AgentTool`` list,
not the protocol path.

Security
~~~~~~~~

* External MCP tools execute network requests on behalf of the user.
  The chat router is responsible for gating them through
  ``permission_check`` if/when a policy applies. By default the loop
  treats them like every other ``AgentTool``.
* Bearer headers in the config blob live in the database and are
  never echoed to the model — only the resolved request reaches the
  remote server. The agent sees the **tool name + description** the
  server returned, not the URL.
* Request + response timeouts are hard-capped at
  :data:`_MCP_REQUEST_TIMEOUT_SECONDS` and the response body is
  truncated at :data:`_MCP_RESPONSE_MAX_BYTES` before being returned
  to the agent so a runaway server can't OOM a turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.core.agent_loop.types import AgentTool
from app.core.tools.display import make_tool_display
from app.core.tools.errors import ToolError, ToolErrorCode

log = logging.getLogger(__name__)

# Wall-clock cap on a single MCP request. Generous enough for slow
# servers but tight enough that a broken endpoint doesn't block a
# turn for minutes.
_MCP_REQUEST_TIMEOUT_SECONDS = 30.0

# Response bytes cap forwarded to the agent. The body is decoded and
# truncated with a clear marker so the model sees the start of a long
# response rather than nothing.
_MCP_RESPONSE_MAX_BYTES = 32_000

# Maximum number of tools we publish per server. Stops a misconfigured
# server from registering hundreds of tools and crowding the agent's
# tool catalogue.
_MAX_TOOLS_PER_SERVER = 64

# Default transport when a config doesn't specify one. HTTP is the
# common modern shape; stdio support lands on demand.
_DEFAULT_TRANSPORT = "http"


def build_external_mcp_tools(
    server_configs: list[dict[str, Any]],
) -> list[AgentTool]:
    """Return cross-provider ``AgentTool``s for every enabled MCP server.

    Args:
        server_configs: list of ``{"name", "config"}`` dicts. ``name``
            is the user-friendly identifier (used as the tool-name
            prefix); ``config`` is the decoded JSON config object.
            Caller filters by ``status == "enabled"``.

    Returns:
        A flattened list of ``AgentTool`` instances ready to append to
        the chat router's tool list. Servers that fail discovery are
        logged and silently dropped so the rest of the chat surface
        keeps working.
    """
    out: list[AgentTool] = []
    for entry in server_configs:
        name = str(entry.get("name") or "").strip()
        config = entry.get("config") or {}
        if not name or not isinstance(config, dict):
            log.warning("MCP_BAD_SERVER_ENTRY skipping name=%r", name)
            continue
        out.extend(_tools_for_server(server_name=name, config=config))
    return out


def _tools_for_server(*, server_name: str, config: dict[str, Any]) -> list[AgentTool]:
    """Wrap one server's published tools, one ``AgentTool`` per remote tool."""
    transport = str(config.get("transport") or _DEFAULT_TRANSPORT).lower()
    if transport != "http":
        log.warning(
            "MCP_UNSUPPORTED_TRANSPORT server=%s transport=%s — skipping",
            server_name,
            transport,
        )
        return []
    url = str(config.get("url") or "").strip()
    if not url:
        log.warning("MCP_NO_URL server=%s — skipping", server_name)
        return []
    headers = config.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}

    discovered = _list_tools_sync(server_name=server_name, url=url, headers=headers)
    out: list[AgentTool] = []
    for spec in discovered[:_MAX_TOOLS_PER_SERVER]:
        tool = _wrap_remote_tool(
            server_name=server_name,
            url=url,
            headers=headers,
            spec=spec,
        )
        if tool is not None:
            out.append(tool)
    return out


def _list_tools_sync(
    *,
    server_name: str,
    url: str,
    headers: dict[str, Any],
) -> list[dict[str, Any]]:
    """Block once on a fresh event loop to fetch the tool inventory.

    External MCP tool discovery is rare (once per turn, on cold boot)
    and cheap enough that paying for one ``asyncio.run`` here keeps
    the factory sync — matching every other AgentTool factory in the
    project. The actual remote ``call_tool`` invocations stay async.
    """
    try:
        return asyncio.run(_list_tools_async(url=url, headers=headers))
    except RuntimeError:
        # Already running inside an event loop (rare — only used by
        # tests that mount the bridge from an async context). Fall
        # back to scheduling onto the current loop.
        loop = asyncio.get_event_loop()
        future = asyncio.run_coroutine_threadsafe(_list_tools_async(url=url, headers=headers), loop)
        return future.result(timeout=_MCP_REQUEST_TIMEOUT_SECONDS)
    except (TimeoutError, httpx.HTTPError) as exc:
        log.warning("MCP_DISCOVER_FAILED server=%s url=%s error=%s", server_name, url, exc)
        return []
    except Exception:
        log.exception("MCP_DISCOVER_UNEXPECTED server=%s", server_name)
        return []


async def _list_tools_async(
    *,
    url: str,
    headers: dict[str, Any],
) -> list[dict[str, Any]]:
    """Issue a single ``POST /list_tools`` request and parse the response."""
    async with httpx.AsyncClient(timeout=_MCP_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{url.rstrip('/')}/list_tools",
            headers={**headers, "Content-Type": "application/json"},
            json={},
        )
        response.raise_for_status()
        payload = response.json()
    tools = payload.get("tools") if isinstance(payload, dict) else None
    if not isinstance(tools, list):
        return []
    return [t for t in tools if isinstance(t, dict)]


def _wrap_remote_tool(
    *,
    server_name: str,
    url: str,
    headers: dict[str, Any],
    spec: dict[str, Any],
) -> AgentTool | None:
    """Build one :class:`AgentTool` proxying a single remote MCP tool."""
    tool_name = str(spec.get("name") or "").strip()
    description = str(spec.get("description") or "").strip()
    parameters = (
        spec.get("input_schema")
        or spec.get("parameters")
        or {
            "type": "object",
            "properties": {},
            "required": [],
        }
    )
    if not tool_name:
        return None
    qualified = f"mcp_{_sanitize(server_name)}_{_sanitize(tool_name)}"

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        del tool_call_id  # unused — remote server doesn't need it
        try:
            return await _call_remote_tool(
                url=url,
                headers=headers,
                tool_name=tool_name,
                arguments=kwargs,
            )
        except httpx.HTTPError as exc:
            log.warning(
                "MCP_CALL_FAILED server=%s tool=%s error=%s",
                server_name,
                tool_name,
                exc,
            )
            return ToolError(
                ToolErrorCode.IO_ERROR,
                f"External MCP server '{server_name}' tool '{tool_name}' failed: {exc}",
            ).render()
        except (TimeoutError, json.JSONDecodeError) as exc:
            return ToolError(
                ToolErrorCode.IO_ERROR,
                f"External MCP server '{server_name}' tool '{tool_name}': {exc}",
            ).render()

    return AgentTool(
        name=qualified,
        description=description or f"External MCP tool from {server_name}.",
        parameters=parameters if isinstance(parameters, dict) else {},
        execute=execute,
        display=make_tool_display(
            icon="🔌",
            label=f"{server_name}.{tool_name}",
            present=lambda _args: f"🔌 Calling {server_name}.{tool_name}",
            compact=lambda _args: f"{server_name}.{tool_name}(...)",
        ),
    )


async def _call_remote_tool(
    *,
    url: str,
    headers: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """Issue a single ``POST /call_tool`` request and decode the response."""
    async with httpx.AsyncClient(timeout=_MCP_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{url.rstrip('/')}/call_tool",
            headers={**headers, "Content-Type": "application/json"},
            json={"name": tool_name, "arguments": arguments},
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        return _bounded(str(payload))
    if payload.get("is_error"):
        return ToolError(
            ToolErrorCode.IO_ERROR,
            _bounded(str(payload.get("content") or "remote MCP error")),
        ).render()
    content = payload.get("content")
    if isinstance(content, str):
        return _bounded(content)
    return _bounded(json.dumps(content, ensure_ascii=False))


def _bounded(text: str) -> str:
    """Truncate ``text`` to :data:`_MCP_RESPONSE_MAX_BYTES` with a marker."""
    encoded = text.encode("utf-8")
    if len(encoded) <= _MCP_RESPONSE_MAX_BYTES:
        return text
    return encoded[:_MCP_RESPONSE_MAX_BYTES].decode("utf-8", errors="ignore") + "…[truncated]"


def _sanitize(name: str) -> str:
    """Coerce ``name`` to a stable identifier suitable for ``AgentTool.name``."""
    safe = "".join(c if c.isalnum() else "_" for c in name).strip("_")
    return safe or "tool"
