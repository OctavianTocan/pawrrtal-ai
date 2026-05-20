"""Per-request ``ClaudeAgentOptions`` assembly for the Claude provider.

Extracted from :mod:`app.core.providers.claude.provider` so the
``ClaudeLLM`` class stays under the project's 500-line file budget.
Pure function: given the static :class:`ClaudeLLMConfig` plus the
per-turn overrides the caller supplied, return the
:class:`ClaudeAgentOptions` instance the SDK expects.

This module does not own any state — the stderr callback and stored
``ClaudeLLMConfig`` come from the provider instance via callable +
config arguments. That keeps the per-request behaviour testable
without instantiating a full ``ClaudeLLM``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import ClaudeAgentOptions

from app.core.agent_loop.types import AgentTool, PermissionCheckFn
from app.core.config import settings as _settings
from app.core.providers.base import ReasoningEffort
from app.core.providers.claude.tool_bridge import make_can_use_tool
from app.core.providers.claude.tools import _merge_agent_tools_into_whitelist

if TYPE_CHECKING:
    from app.core.providers.claude.provider import ClaudeLLMConfig

# Single-turn chat default; widened automatically when tool use is enabled
# so the agent can read its own tool result on the next turn.
_DEFAULT_MAX_TURNS = 1

# When tool use is enabled (e.g. ``exa_search``), the agent needs at
# least one extra turn to read the tool result and respond. We budget
# a few more so the model can plan → call tool → read result → maybe
# refine with a follow-up call → respond. ``error_max_turns`` surfaces
# as a ``ResultMessage(is_error=True)`` and is the symptom users see
# when this number is too low.
_TOOL_ENABLED_MAX_TURNS = 6

# Pawrrtal's five-level ``ReasoningEffort`` literal collapses onto
# Claude's three documented adaptive-thinking levels (low/medium/high
# per https://docs.claude.com/en/docs/build-with-claude/extended-thinking).
# ``minimal`` rounds up to ``low`` and ``extra-high`` saturates at
# ``high``. The chat-router resolver normally adapts these before we
# get here — this mapping is belt-and-braces.
_CLAUDE_EFFORT_MAP: dict[str, str] = {
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "extra-high": "high",
}


def build_options(
    *,
    config: ClaudeLLMConfig,
    workspace_root: Path | None,
    conversation_id: uuid.UUID,
    sdk_model: str,
    stderr_callback: Callable[[str], None],
    session_probe: Callable[[str, str | None], bool],
    system_prompt: str | None = None,
    agent_tools: list[AgentTool] | None = None,
    reasoning_effort: ReasoningEffort | None = None,
    permission_check: PermissionCheckFn | None = None,
    force_fresh_session: bool = False,
) -> ClaudeAgentOptions:
    """Assemble :class:`ClaudeAgentOptions` for one ``query()`` call.

    Args:
        config: The provider's stored configuration (tools whitelist,
            max_turns, system prompt, cwd, env, …).
        workspace_root: Optional workspace root used for per-workspace
            API-key lookup via :func:`app.core.keys.resolve_api_key`.
            ``None`` falls back to the static ``oauth_token`` on
            ``config``.
        conversation_id: App-level conversation UUID; reused as the
            Claude SDK session id.
        sdk_model: The SDK-side model string (already mapped via
            :func:`_resolve_sdk_model`).
        stderr_callback: Bound method on the provider instance —
            captures CLI stderr lines into a rolling diagnostic buffer.
        session_probe: Callable that returns ``True`` when the SDK
            already has a transcript for ``conversation_id``. Used to
            decide ``session_id=`` vs ``resume=``.
        system_prompt: Optional per-call override.  When provided,
            takes precedence over ``config.system_prompt`` so the chat
            router can inject app-assembled context (e.g. workspace
            AGENTS.md per PR #113).
        agent_tools: Cross-provider :class:`AgentTool` list assembled
            by the chat router.  Translated into a single in-process
            MCP server via :mod:`.tool_bridge` and mounted under
            ``ClaudeAgentOptions.mcp_servers``; the matching
            ``mcp__pawrrtal__<name>`` IDs are appended to the
            allowed-tools whitelist so the SDK actually permits
            execution.
        reasoning_effort: Optional per-turn reasoning-depth knob.
        permission_check: Optional cross-provider permission gate.
            When supplied, bound into ``ClaudeAgentOptions.can_use_tool``
            via :func:`.tool_bridge.make_can_use_tool` so the SDK
            enforces the same policy as the Gemini path.
        force_fresh_session: When True, skips the resume probe and
            seeds a brand-new SDK session.  Used by the resume-failure
            fallback path in :meth:`ClaudeLLM.stream` so a single
            conversation can recover from a missing transcript without
            500ing.
    """
    session_id = str(conversation_id)

    # Local tool whitelist for the Claude SDK's built-in CLI tools
    # (read/write filesystem, etc.).  Distinct from ``agent_tools`` —
    # those are app-defined tools we bridge into an MCP server.
    local_tools = list(config.tools) if config.tools is not None else None
    mcp_servers: dict[str, Any] = {}

    # Bridge the cross-provider AgentTool list into a single MCP
    # server.  All app-defined tools (workspace files, web search, …)
    # flow through here — the provider doesn't know which ones are in
    # the list and shouldn't.
    local_tools = _merge_agent_tools_into_whitelist(
        local_tools, list(agent_tools or []), mcp_servers
    )

    # If tool use is enabled but the caller didn't override
    # ``max_turns``, automatically widen the turn budget so the agent
    # can read its own tool result. Without this the very first tool
    # invocation hits the SDK's ``error_max_turns`` and surfaces in
    # chat as a "Claude SDK result reported an error" panel
    # immediately after the "Searched the web" indicator.
    effective_max_turns = config.max_turns
    tool_use_enabled = bool(local_tools) or bool(mcp_servers)
    if tool_use_enabled and effective_max_turns <= _DEFAULT_MAX_TURNS:
        effective_max_turns = _TOOL_ENABLED_MAX_TURNS

    # System prompt resolution: per-call value (from the chat router /
    # AGENTS.md loader) wins over ``config.system_prompt``.
    effective_system_prompt = system_prompt or config.system_prompt

    # Full SDK isolation: ``setting_sources=[]`` disables every
    # filesystem-driven source the bundled CLI would otherwise read
    # from cwd — ``CLAUDE.md``, ``.claude/settings.json`` (hooks!),
    # and the project's ``.mcp.json`` MCP-server registration. Without
    # this, an unset ``cwd`` falls back to the uvicorn process
    # directory, and the SDK ingests the *host repo's* files instead
    # of the user workspace.
    #
    # We do not lose the workspace ``CLAUDE.md`` by doing this:
    # ``channels.turn_runner._workspace_system_prompt`` already
    # injects it via ``system_prompt=`` from the user's actual
    # workspace root, which is the only directory we should be
    # reading. The previous ``["project"]`` branch was reading the
    # wrong project (the backend repo) — not "defence in depth",
    # just a leak.
    setting_sources: list[str] = []
    kwargs: dict[str, Any] = {
        "model": sdk_model,
        "tools": local_tools,
        "max_turns": effective_max_turns,
        "permission_mode": config.permission_mode,
        "system_prompt": effective_system_prompt,
        "setting_sources": setting_sources,
        "stderr": stderr_callback,
    }
    if reasoning_effort is not None:
        # The Claude API's adaptive thinking ``effort`` enum is
        # documented as ``low | medium | high`` only (see
        # https://docs.claude.com/en/docs/build-with-claude/extended-thinking).
        # Pawrrtal's ``minimal`` collapses to ``low`` and ``extra-high``
        # saturates at ``high`` — so a user who picked the lightest or
        # heaviest level on a model that supports the full five-step
        # ladder still gets the closest level Claude exposes.
        kwargs["effort"] = _CLAUDE_EFFORT_MAP.get(reasoning_effort, reasoning_effort)
    # Per-request cost cap (PR 04). The Claude SDK enforces this
    # natively — when the agent burns past ``max_budget_usd`` mid-turn,
    # the SDK terminates with a ``ResultMessage(is_error=True,
    # subtype="error_max_budget")``. Zero / negative disables.
    if _settings.cost_tracker_enabled and _settings.cost_max_per_request_usd > 0:
        kwargs["max_budget_usd"] = _settings.cost_max_per_request_usd
    # Claude SDK sandbox (PR 05). Off by default; flip
    # ``CLAUDE_SANDBOX_ENABLED=true`` to wrap the bundled CLI in the
    # SDK's macOS Seatbelt sandbox.
    if _settings.claude_sandbox_enabled:
        kwargs["sandbox"] = {
            "enabled": True,
            "autoAllowBashIfSandboxed": _settings.claude_sandbox_auto_allow_bash,
            "excludedCommands": _settings.claude_sandbox_excluded_commands_list,
        }
    if mcp_servers:
        kwargs["mcp_servers"] = mcp_servers
        # ``can_use_tool`` is the SDK's per-call permission hook. When
        # the chat router supplies a cross-provider ``permission_check``
        # (PR 03b), we delegate to it so Claude and Gemini enforce the
        # same policy.  Without one, the bridge falls back to
        # namespace-only approval (the historical behaviour from PR
        # #131). Either way the whitelist on ``tools=`` is necessary
        # but not sufficient — without ``can_use_tool`` the SDK blocks
        # every custom MCP tool call.
        kwargs["can_use_tool"] = make_can_use_tool(permission_check)
    if config.cwd is not None:
        kwargs["cwd"] = config.cwd

    env = _build_env(config, workspace_root)
    if env:
        kwargs["env"] = env

    # First turn: seed a brand-new SDK session that uses the same UUID
    # as our conversation. Subsequent turns: resume it.
    # ``force_fresh_session`` (PR 05) skips the resume probe so the
    # resume-failure fallback path in :meth:`ClaudeLLM.stream` can
    # re-issue the same conversation as a fresh session.
    if not force_fresh_session and session_probe(session_id, config.cwd):
        kwargs["resume"] = session_id
    else:
        kwargs["session_id"] = session_id

    return ClaudeAgentOptions(**kwargs)


def _build_env(config: ClaudeLLMConfig, workspace_root: Path | None) -> dict[str, str]:
    """Compose the env dict forwarded to the CLI subprocess.

    Workspace-scoped OAuth lookups happen via
    :func:`app.core.keys.resolve_api_key`. When no workspace is bound
    we fall back to the static ``oauth_token`` on the config (set by
    the factory from ``settings``).
    """
    # Imported here to avoid an import cycle with provider.py — the
    # provider imports from this module at module load.
    from app.core.keys import resolve_api_key  # noqa: PLC0415

    env: dict[str, str] = dict(config.extra_env)
    if workspace_root is not None:
        token = resolve_api_key(workspace_root, "CLAUDE_CODE_OAUTH_TOKEN")
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    elif config.oauth_token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = config.oauth_token
    return env
