"""Bridge Pawrrtal AgentTools into Codex SDK dynamic tools."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.agents.permissions import default_tool_permission_check, render_permission_denied
from app.agents.types import AgentTool

logger = logging.getLogger(__name__)

CODEX_DYNAMIC_TOOL_METHOD = "item/tool/call"
PAWRRTAL_DYNAMIC_TOOL_NAMESPACE = "pawrrtal"

_DENY_ALL_DECISION: dict[str, str] = {"decision": "deny"}
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


@dataclass(frozen=True)
class _ToolContext:
    """Active Pawrrtal tools available to one native Codex thread."""

    tools: dict[str, AgentTool]


class CodexDynamicToolBridge:
    """Sync JSON-RPC request handler that executes Pawrrtal tools for Codex."""

    def __init__(self) -> None:
        self._contexts: dict[str, _ToolContext] = {}

    @contextmanager
    def activate(
        self,
        *,
        thread_id: str | None,
        tools: list[AgentTool] | None,
    ) -> Iterator[None]:
        """Register tools for one active Codex thread while its turn streams."""
        if not thread_id or not tools:
            yield
            return
        self._contexts[thread_id] = _ToolContext(tools={tool.name: tool for tool in tools})
        try:
            yield
        finally:
            self._contexts.pop(thread_id, None)

    def handle_request(self, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        """Handle Codex app-server requests without letting SDK defaults approve writes."""
        if method in (
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        ):
            return _DENY_ALL_DECISION
        if method != CODEX_DYNAMIC_TOOL_METHOD:
            return {}
        return self._handle_dynamic_tool_call(params or {})

    def _handle_dynamic_tool_call(self, params: dict[str, Any]) -> dict[str, Any]:
        thread_id = _str_param(params, "threadId")
        call_id = _str_param(params, "callId") or "codex-dynamic-tool"
        tool_name = _str_param(params, "tool")
        context = self._contexts.get(thread_id)
        tool = context.tools.get(tool_name) if context and tool_name else None
        if context is None or tool is None:
            return _tool_response(f"Tool '{tool_name or '<missing>'}' is not available.", False)
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            return _tool_response("Tool arguments must be a JSON object.", False)
        denial = default_tool_permission_check(tool, call_id, arguments)
        if denial is not None:
            return _tool_response(render_permission_denied(denial), False)
        started_at = time.monotonic()
        try:
            result = asyncio.run(_execute_tool(tool, call_id, arguments))
        except Exception as exc:
            logger.exception("openai_codex dynamic tool failed: %s", tool_name)
            return _tool_response(f"Tool error: {exc}", False)
        duration_ms = (time.monotonic() - started_at) * 1000.0
        logger.info(
            "openai_codex dynamic tool completed name=%s duration_ms=%.1f", tool_name, duration_ms
        )
        return _tool_response(result, True)


def dynamic_tool_specs(tools: list[AgentTool] | None) -> list[dict[str, Any]]:
    """Convert Pawrrtal tools to raw Codex ``dynamicTools`` specs."""
    specs: list[dict[str, Any]] = []
    for tool in tools or []:
        if not _IDENTIFIER_RE.fullmatch(tool.name):
            logger.warning("openai_codex: skipping invalid dynamic tool name=%r", tool.name)
            continue
        specs.append(
            {
                "namespace": PAWRRTAL_DYNAMIC_TOOL_NAMESPACE,
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.parameters,
                "deferLoading": False,
            }
        )
    return specs


async def _execute_tool(
    tool: AgentTool,
    call_id: str,
    arguments: dict[str, Any],
) -> str:
    return await tool.execute(call_id, **arguments)


def dynamic_tool_fingerprint(tools: list[AgentTool] | None) -> str:
    """Stable fingerprint for thread reuse when the Pawrrtal tool surface changes."""
    payload = json.dumps(dynamic_tool_specs(tools), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def thread_start_payload(
    *,
    model_id: str,
    workspace_root: str | None,
    system_prompt: str | None,
    developer_instructions: str,
    tools: list[AgentTool] | None,
) -> dict[str, Any]:
    """Build the raw SDK payload needed for experimental dynamic tools."""
    payload: dict[str, Any] = {
        "model": model_id,
        "cwd": workspace_root,
        "baseInstructions": system_prompt,
        "developerInstructions": developer_instructions,
        "approvalPolicy": "never",
        "sandbox": "read-only",
    }
    specs = dynamic_tool_specs(tools)
    if specs:
        payload["dynamicTools"] = specs
    return payload


async def start_codex_thread(codex: Any, payload: dict[str, Any]) -> Any:
    """Start a Codex thread, using raw JSON-RPC when dynamic tools are present."""
    if not payload.get("dynamicTools"):
        return await codex.thread_start(
            model=payload["model"],
            cwd=payload.get("cwd"),
            base_instructions=payload.get("baseInstructions"),
            developer_instructions=payload.get("developerInstructions"),
            approval_mode=_approval_mode(),
            sandbox=_sandbox_mode(),
        )
    client = getattr(codex, "_client", None)
    if client is None:
        raise RuntimeError("Codex SDK client is unavailable for dynamic tool thread startup.")
    started = await client.thread_start(payload)
    thread_id = getattr(getattr(started, "thread", None), "id", None)
    if not isinstance(thread_id, str) or not thread_id:
        raise RuntimeError("Codex dynamic tool thread_start did not return a thread id.")
    from openai_codex import AsyncThread  # noqa: PLC0415

    return AsyncThread(codex, thread_id)


def _approval_mode() -> Any:
    from openai_codex import ApprovalMode  # noqa: PLC0415

    return ApprovalMode.deny_all


def _sandbox_mode() -> Any:
    from openai_codex.generated.v2_all import SandboxMode  # noqa: PLC0415

    return SandboxMode.read_only


def _tool_response(content: str, success: bool) -> dict[str, Any]:
    return {
        "contentItems": [{"type": "inputText", "text": content}],
        "success": success,
    }


def _str_param(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    return value if isinstance(value, str) else ""
