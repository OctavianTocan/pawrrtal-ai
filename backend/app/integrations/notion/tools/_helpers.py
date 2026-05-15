"""Shared helpers for Notion tool factories.

Pulling these out of every per-category module keeps the tool files
short and ensures all eighteen tools format their error responses
the same way (which the agent's downstream parsing depends on).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.keys import resolve_api_key
from app.core.plugins.types import ToolContext

NOTION_API_KEY_NAME = "NOTION_API_KEY"


def resolve_workspace_token(ctx: ToolContext) -> str | None:
    """Return the workspace's ``NOTION_API_KEY`` or ``None`` when unset.

    Centralised so every tool factory uses the same resolver / key
    name; if Notion ever expands the env-key surface the change lands
    in exactly one place.
    """
    return resolve_api_key(ctx.workspace_id, NOTION_API_KEY_NAME)


def encode_error(message: str) -> str:
    """Render a stable JSON error string for the agent.

    Matches openclaw-notion's ``{"error": "..."}`` shape so prompts that
    branch on the error envelope keep working unchanged.
    """
    return json.dumps({"error": message})


def encode_result(payload: Any) -> str:
    """Render a successful tool result as JSON for the LLM.

    Notion responses are deeply structured; the LLM is more accurate
    consuming the JSON verbatim than a paraphrased prose summary, so
    we serialise straight through and let the model reason over it.
    """
    return json.dumps(payload, ensure_ascii=False)


def build_tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    execute: Callable[[str, dict[str, Any]], Awaitable[str]],
) -> AgentTool:
    """Wire an ``AgentTool`` from a parameter schema and an async handler.

    Centralises the kwargs → dict marshaling so each per-tool factory
    can focus on the actual logic.
    """

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        # Coerce kwargs straight through — the agent loop already
        # validated them against ``parameters`` (a JSON schema) on the
        # provider side, so we trust the keys here.
        return await execute(tool_call_id, dict(kwargs))

    return AgentTool(
        name=name,
        description=description,
        parameters=parameters,
        execute=_execute,
    )


def require_token(ctx: ToolContext) -> str | None:
    """Return the token or ``None``; tools surface a clean error on miss.

    Activation gating already keeps tools off the list when
    ``NOTION_API_KEY`` isn't configured, but a race (key cleared
    mid-turn) could still produce a missing token at execute time.
    Surfacing a friendly message beats letting ``ntn`` exit non-zero
    with an opaque auth error.
    """
    return resolve_workspace_token(ctx)


def missing_token_error() -> str:
    """Stable error string when the workspace token is gone at exec time."""
    return encode_error(
        "Notion is not configured for this workspace. Add a NOTION_API_KEY in Settings → Workspace."
    )
