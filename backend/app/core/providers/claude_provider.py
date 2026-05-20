"""Claude Agent SDK provider.

Wraps :func:`claude_agent_sdk.query` to expose a streaming chat interface
that matches the rest of the :class:`AILLM` protocol — every tick
becomes a :class:`StreamEvent` dictionary.

Notable design decisions:

- **Session continuity** maps each app-level ``conversation_id`` onto a
  Claude SDK session ID with the same value. The first turn passes
  ``session_id=str(conversation_id)`` to seed a brand-new session;
  subsequent turns pass ``resume=str(conversation_id)`` to reload the
  history. We detect "first turn" via :func:`claude_agent_sdk.get_session_info`,
  which is a cheap stat on the local Claude transcript directory.

- **Tool surface** is locked down via ``tools=[]`` by default. The chat
  endpoint doesn't expect filesystem access from the model; disabling
  tools removes an entire class of accidental exposure (Bash, Edit,
  Write, WebFetch, ...).

- **Setting sources** are pinned to ``[]`` so the agent never inherits
  ``~/.claude/settings.json`` files, hooks, or skills from the developer
  machine. This is the SDK's "isolation" mode.

- **System prompt** is a chat-scoped one — not Claude Code's
  software-engineer default — so the model behaves like a chat assistant
  on this surface.

- **Errors** are caught at every documented SDK error type and converted
  into ``StreamEvent(type="error")`` so the chat endpoint surfaces them
  as SSE events instead of crashing the connection.

- **OAuth token** is forwarded explicitly to the subprocess via
  ``ClaudeAgentOptions.env``. Pydantic-settings reads ``.env`` files but
  does not push the values back into ``os.environ``, so the bundled CLI
  subprocess would otherwise miss the token.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKError,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    PermissionMode,
    ProcessError,
    get_session_info,
    query,
)

from app.core.agent_loop.display import tool_display_map
from app.core.agent_loop.types import AgentTool, PermissionCheckFn
from app.core.agent_system_prompt import (
    DEFAULT_AGENT_SYSTEM_PROMPT as _DEFAULT_SYSTEM_PROMPT,
)
from app.core.config import settings as _settings
from app.core.keys import resolve_api_key

from ._claude_tool_bridge import (
    MCP_SERVER_NAME as AGENT_TOOL_MCP_SERVER_NAME,
)
from ._claude_tool_bridge import (
    allowed_tool_ids,
    build_mcp_server,
    claude_tool_id,
    make_can_use_tool,
)
from .base import ReasoningEffort, StreamEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults — tunable at construction time via :class:`ClaudeLLMConfig`.
# ---------------------------------------------------------------------------

# Map our frontend model IDs to Claude SDK model strings. The frontend uses
# Anthropic marketing names ("4-6", "4-7"); the Claude SDK accepts the API
# model IDs directly. When a stable alias arrives upstream we can drop the
# mapping; for now we pin explicitly so a typo at the frontend layer fails
# loudly here.
_MODEL_MAP: dict[str, str] = {
    "claude-haiku-4-5": "claude-haiku-4-5",
    "claude-sonnet-4-5": "claude-sonnet-4-5",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-opus-4-5": "claude-opus-4-5",
    "claude-opus-4-6": "claude-opus-4-6",
    "claude-opus-4-7": "claude-opus-4-7",
}

# Empty list disables every built-in tool. Safest default for a chat
# surface — the model can't read files, run bash, or fetch URLs.
_DEFAULT_TOOLS: list[str] = []

# Single-turn chat: each user message produces exactly one assistant
# response; the SDK closes the subprocess after that turn.
_DEFAULT_MAX_TURNS = 1

# When tool use is enabled (e.g. ``exa_search``), the agent needs at
# least one extra turn to read the tool result and respond. We budget a
# few more so the model can plan → call tool → read result → maybe
# refine with a follow-up call → respond. ``error_max_turns`` surfaces
# as a ``ResultMessage(is_error=True)`` and is the symptom users see when
# this number is too low (the chat shows an error panel after a
# successful "Searched the web" indicator).
_TOOL_ENABLED_MAX_TURNS = 6

# With ``tools=[]`` no tool ever runs, so the choice here is mostly
# cosmetic. We pick "default" rather than "bypassPermissions" so that
# enabling a tool in the future fails closed instead of open.
_DEFAULT_PERMISSION_MODE: PermissionMode = "default"

# Last N CLI stderr lines kept in the rolling buffer for diagnostics
# on a ``ProcessError``.  Bounded so a chatty subprocess can't grow
# the buffer without bound.
_STDERR_TAIL_LINES = 20

# Cap on the per-retry sleep — even with the configured exponential
# backoff we don't want a single transient blip to wedge the request
# for minutes.
_RETRY_SLEEP_CEILING_SECONDS = 30.0

# Pawrrtal's five-level ``ReasoningEffort`` literal collapses onto
# Claude's three documented adaptive-thinking levels (low/medium/high
# per https://docs.claude.com/en/docs/build-with-claude/extended-thinking).
# ``minimal`` rounds up to ``low`` (Claude has no faster tier) and
# ``extra-high`` saturates at ``high``. The chat-router resolver
# normally adapts these before we get here because no Claude catalog
# row lists either level — this is the belt-and-braces.
_CLAUDE_EFFORT_MAP: dict[str, str] = {
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "extra-high": "high",
}

# System prompt scoped to a chat product. We deliberately do NOT use
# Claude Code's default preset, which steers the model toward software
# engineering tasks and tools that don't exist in this surface.
# Provider-default system prompt: when no caller supplied one we use
# the *shared* ``app.core.agent_system_prompt.DEFAULT_AGENT_SYSTEM_PROMPT``
# so the agent's identity doesn't silently change based on which
# model the user picked.  The real prompt for chat traffic is
# assembled from SOUL.md + AGENTS.md by the chat router (PR #113);
# this constant only fires for unit tests and script-mode callers.


# ---------------------------------------------------------------------------
# Public configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaudeLLMConfig:
    """Tunable configuration for :class:`ClaudeLLM`.

    Each field has a safe default; pass an instance to ``ClaudeLLM``
    when you need to override one (most often in tests).
    """

    tools: list[str] | None = field(default_factory=lambda: list(_DEFAULT_TOOLS))
    """Whitelist of built-in tools the agent may use. ``[]`` (default) disables every built-in tool. ``None`` falls back to the SDK / CLI defaults — only do that on a trusted machine."""

    max_turns: int = _DEFAULT_MAX_TURNS
    """Maximum number of conversation turns inside a single ``stream()`` call."""

    permission_mode: PermissionMode = _DEFAULT_PERMISSION_MODE
    """SDK permission mode. Effective only when at least one tool is enabled."""

    system_prompt: str | None = _DEFAULT_SYSTEM_PROMPT
    """System prompt sent on every turn. ``None`` falls back to the SDK default."""

    cwd: str | None = None
    """Working directory passed to the SDK. Affects where transcript files live and where tools (if any) operate. ``None`` falls back to the process cwd."""

    oauth_token: str | None = None
    """OAuth token forwarded to the CLI subprocess as ``CLAUDE_CODE_OAUTH_TOKEN``. ``None`` defers to whatever is already on the parent process's ``os.environ``."""

    extra_env: dict[str, str] = field(default_factory=dict)
    """Additional environment variables forwarded to the CLI subprocess."""


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class ClaudeLLM:
    """Wraps the Claude Agent SDK for streaming chat."""

    def __init__(
        self,
        model_id: str,
        *,
        config: ClaudeLLMConfig | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        """Construct a Claude provider bound to a specific model slug.

        Args:
            model_id: The bare vendor slug (e.g. ``"claude-sonnet-4-6"``),
                **not** the canonical wire form. The factory calls
                :func:`parse_model_id` first and hands the unwrapped
                ``parsed.model`` slug here; ``_MODEL_MAP`` is keyed on
                bare slugs by design.
            config: Optional Claude-specific config (OAuth token,
                ``max_turns``, extra env). Defaults are read by the
                factory from ``settings``.
            workspace_root: Absolute path from the ``workspaces.path`` DB
                column. When set, ``stream()`` resolves per-workspace
                API-key overrides through
                :func:`app.core.keys.resolve_api_key`.
        """
        self._model_id = model_id
        self._config = config or ClaudeLLMConfig()
        self._workspace_root = workspace_root
        # PR 05: rolling buffer for the last few CLI stderr lines so a
        # ``ProcessError`` can surface useful diagnostic context.
        self._stderr_buffer: list[str] = []

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        history: list[dict[str, str]] | None = None,
        tools: list[AgentTool] | None = None,
        system_prompt: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        permission_check: PermissionCheckFn | None = None,
        images: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a single assistant response for ``question``.

        Args:
            question: The user message to send to Claude.
            conversation_id: App-level conversation UUID; reused as the
                Claude SDK session ID so multi-turn history is preserved
                across requests.
            user_id: App-level user UUID. Currently unused by this
                provider but kept in the protocol so future per-user
                cwd / quota logic can wire in without a signature change.
            history: Per-conversation message history loaded by the
                chat router from ``chat_messages``. When the Claude
                SDK already has a transcript for this ``conversation_id``
                we rely on ``resume=`` (Claude's native continuity).
                When the transcript is missing — typically because the
                user previously chatted on a different provider
                (Gemini, etc.) — we prepend a bounded summary of
                ``history`` to the user's question so the model sees
                the prior turns. Closes #308.
            tools: Optional list of cross-provider :class:`AgentTool`
                instances. Bridged into a single in-process MCP server
                by ``_claude_tool_bridge`` so the SDK can call them.
            system_prompt: Optional system prompt to override the
                provider-default chat-scoped prompt. Falls back to
                :data:`DEFAULT_AGENT_SYSTEM_PROMPT` when ``None``.
            reasoning_effort: Optional reasoning-depth knob. Forwarded to
                Claude Code as ``effort`` when set.
            permission_check: Optional cross-provider ``can_use_tool``
                gate (PR 03b).  Bound into the Claude SDK's
                ``can_use_tool`` callback via
                :func:`_claude_tool_bridge.make_can_use_tool` so the
                same policy applies as the Gemini path.  ``None``
                preserves the historical namespace-only auto-approval.
            images: Optional list of multimodal image inputs (PR 05).
                Each dict has ``data`` (base64 string) and ``media_type``
                (e.g. ``image/png``); they're rendered as Claude SDK
                content blocks alongside the text question.

        Yields:
            ``StreamEvent`` dictionaries — text/thinking deltas, tool
            events, an optional rate-limit warning, and any error events.
        """
        # PR 05: retry-with-backoff for transient connection blips +
        # resume-failure auto-fallback to a fresh session.  Both are
        # gated on whether we've already yielded any event to the
        # caller — once events are on the wire we can't safely retry
        # without producing duplicates, so the inner generator
        # propagates as before.
        any_event_yielded = False
        attempt = 0
        max_attempts = max(1, _settings.claude_retry_max_attempts)
        used_resume = _session_exists(str(conversation_id), self._config.cwd)
        display_by_name = _claude_display_map(list(tools or []))
        # #308: when the user switches providers mid-conversation, the
        # Claude SDK has no transcript for this conversation_id yet —
        # but the app does. Replay it as a system-prompt addendum so
        # the model sees the prior turns instead of starting blind.
        # When the SDK already has a session (``used_resume``), we
        # avoid duplicating context — Claude's own transcript wins.
        history_prefix = _render_history_prefix(history) if not used_resume and history else None
        effective_question = f"{history_prefix}\n\n{question}" if history_prefix else question

        while True:
            attempt += 1
            options = self._build_options(
                conversation_id,
                system_prompt=system_prompt,
                agent_tools=tools,
                reasoning_effort=reasoning_effort,
                permission_check=permission_check,
                force_fresh_session=(used_resume and attempt > 1),
            )
            try:
                async for event in _stream_events_for_attempt(
                    prompt=_aiter_user_prompt(effective_question, images),
                    options=options,
                    display_by_name=display_by_name,
                ):
                    any_event_yielded = True
                    yield event
                return
            except CLINotFoundError as error:
                logger.exception("Claude CLI binary not found")
                yield _error_event(
                    "Claude Code CLI binary is not installed in this environment. "
                    "Install it with `npm i -g @anthropic-ai/claude-code` and ensure "
                    "the executable is on PATH, or set ClaudeAgentOptions.cli_path. "
                    f"Underlying error: {error}",
                )
                return
            except CLIConnectionError as error:
                # Resume-failure fallback: an error on a `resume=` call
                # often means the SDK lost the prior session transcript
                # (CLI version drift, transcript file removed, etc.).
                # Try again with `session_id=` so the conversation
                # restarts in place rather than 500ing the user.
                if used_resume and attempt == 1 and not any_event_yielded:
                    logger.warning(
                        "Claude resume failed for session %s; falling back to fresh session: %s",
                        conversation_id,
                        error,
                    )
                    continue
                if (
                    _is_retryable_cli_connection(error)
                    and attempt < max_attempts
                    and not any_event_yielded
                ):
                    delay = _retry_backoff_seconds(attempt)
                    logger.warning(
                        "Claude CLI transient connection error (attempt %d/%d); retrying in %.1fs: %s",
                        attempt,
                        max_attempts,
                        delay,
                        error,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning("Claude CLI subprocess connection lost: %s", error)
                yield _error_event(
                    f"Lost connection to the Claude Code CLI subprocess. Underlying error: {error}",
                )
                return
            except ProcessError as error:
                exit_code = getattr(error, "exit_code", "n/a")
                stderr = getattr(error, "stderr", "")
                stderr_tail = "\n".join(self._stderr_buffer[-_STDERR_TAIL_LINES:])
                logger.exception(
                    "Claude CLI subprocess exited: exit_code=%s stderr=%r captured_tail=%r",
                    exit_code,
                    stderr,
                    stderr_tail,
                )
                yield _error_event(
                    "Claude Code CLI exited with an error. Verify CLAUDE_CODE_OAUTH_TOKEN "
                    "is configured and your account has access to the requested model. "
                    f"Exit code: {exit_code}. stderr: {stderr or stderr_tail!r}",
                )
                return
            except CLIJSONDecodeError:
                logger.exception("Claude CLI returned non-JSON message")
                yield _error_event("Failed to parse a JSON message from the Claude Code CLI.")
                return
            except ClaudeSDKError as error:
                logger.exception("Claude SDK error during stream")
                yield _error_event(f"Claude SDK error: {error}")
                return

    # -- internal --------------------------------------------------------

    def _build_options(
        self,
        conversation_id: uuid.UUID,
        *,
        system_prompt: str | None = None,
        agent_tools: list[AgentTool] | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        permission_check: PermissionCheckFn | None = None,
        force_fresh_session: bool = False,
    ) -> ClaudeAgentOptions:
        """Build per-request options, picking ``session_id`` vs ``resume``.

        Args:
            conversation_id: App-level conversation UUID; reused as the
                Claude SDK session id.
            system_prompt: Optional per-call override.  When provided,
                takes precedence over ``self._config.system_prompt`` so
                the chat router can inject app-assembled context (e.g.
                workspace AGENTS.md per PR #113).
            agent_tools: Cross-provider :class:`AgentTool` list assembled
                by the chat router.  Translated into a single in-process
                MCP server via
                :mod:`app.core.providers._claude_tool_bridge` and mounted
                under ``ClaudeAgentOptions.mcp_servers``; the matching
                ``mcp__pawrrtal__<name>`` IDs are appended to the
                allowed-tools whitelist so the SDK actually permits
            permission_check: Optional cross-provider permission gate.
                When supplied, bound into ``ClaudeAgentOptions.can_use_tool``
                via :func:`_claude_tool_bridge.make_can_use_tool` so the
                SDK enforces the same policy as the Gemini path.
            force_fresh_session: When True, skips the resume probe and
                seeds a brand-new SDK session.  Used by the resume-failure
                fallback path in :meth:`stream` so a single conversation
                can recover from a missing transcript without 500ing.
                execution.
            reasoning_effort: Optional per-turn reasoning-depth knob.
        """
        session_id = str(conversation_id)

        # Local tool whitelist for the Claude SDK's built-in CLI tools
        # (read/write filesystem, etc.).  Distinct from ``agent_tools``
        # — those are app-defined tools we bridge into an MCP server.
        local_tools = list(self._config.tools) if self._config.tools is not None else None
        mcp_servers: dict[str, Any] = {}

        # Bridge the cross-provider AgentTool list into a single MCP
        # server.  All app-defined tools (workspace files, web search,
        # …) flow through here — the provider doesn't know which ones
        # are in the list and shouldn't.
        local_tools = _merge_agent_tools_into_whitelist(
            local_tools, list(agent_tools or []), mcp_servers
        )

        # If tool use is enabled but the caller didn't override
        # ``max_turns``, automatically widen the turn budget so the agent
        # can read its own tool result. Without this the very first
        # tool invocation hits the SDK's ``error_max_turns`` and surfaces
        # in chat as a "Claude SDK result reported an error" panel
        # immediately after the "Searched the web" indicator.
        effective_max_turns = self._config.max_turns
        tool_use_enabled = bool(local_tools) or bool(mcp_servers)
        if tool_use_enabled and effective_max_turns <= _DEFAULT_MAX_TURNS:
            effective_max_turns = _TOOL_ENABLED_MAX_TURNS

        # System prompt resolution: per-call value (from the chat router /
        # AGENTS.md loader) wins over ``self._config.system_prompt``.
        effective_system_prompt = system_prompt or self._config.system_prompt

        # Full SDK isolation: ``setting_sources=[]`` disables every
        # filesystem-driven source the bundled CLI would otherwise
        # read from cwd — ``CLAUDE.md``, ``.claude/settings.json``
        # (hooks!), and the project's ``.mcp.json`` MCP-server
        # registration. Without this, an unset ``cwd`` falls back to
        # the uvicorn process directory, and the SDK ingests the
        # *host repo's* files instead of the user workspace.
        #
        # We do not lose the workspace ``CLAUDE.md`` by doing this:
        # ``channels.turn_runner._workspace_system_prompt`` already
        # injects it via ``system_prompt=`` from the user's actual
        # workspace root, which is the only directory we should be
        # reading. The previous ``["project"]`` branch was reading
        # the wrong project (the backend repo) — not "defence in
        # depth", just a leak.
        setting_sources: list[str] = []
        kwargs: dict[str, Any] = {
            "model": _resolve_sdk_model(self._model_id),
            "tools": local_tools,
            "max_turns": effective_max_turns,
            "permission_mode": self._config.permission_mode,
            "system_prompt": effective_system_prompt,
            "setting_sources": setting_sources,
        }
        if reasoning_effort is not None:
            # The Claude API's adaptive thinking ``effort`` enum is
            # documented as ``low | medium | high`` only (see
            # https://docs.claude.com/en/docs/build-with-claude/extended-thinking).
            # Pawrrtal's ``minimal`` collapses to ``low`` (Claude has
            # no faster tier) and ``extra-high`` saturates at ``high``
            # — so a user who picked the lightest or heaviest level on
            # a model that supports the full five-step ladder still
            # gets the closest level Claude exposes after switching.
            # The catalog's ``supports_reasoning`` tuple should not
            # list ``minimal`` or ``extra-high`` for any Claude model
            # — the chat-router resolver adapts before this line runs
            # — so this mapping is belt-and-braces.
            kwargs["effort"] = _CLAUDE_EFFORT_MAP.get(reasoning_effort, reasoning_effort)
        # Per-request cost cap (PR 04). The Claude SDK enforces this
        # natively — when the agent burns past ``max_budget_usd`` mid-turn,
        # the SDK terminates with a ``ResultMessage(is_error=True,
        # subtype="error_max_budget")``. Zero / negative disables (the
        # SDK treats it as unlimited), so a deployment that doesn't want
        # the cap can leave ``cost_max_per_request_usd=0``.
        if _settings.cost_tracker_enabled and _settings.cost_max_per_request_usd > 0:
            kwargs["max_budget_usd"] = _settings.cost_max_per_request_usd
        # Claude SDK sandbox (PR 05). Off by default; flip
        # ``CLAUDE_SANDBOX_ENABLED=true`` to wrap the bundled CLI in
        # the SDK's macOS Seatbelt sandbox. ``excludedCommands`` is
        # parsed from the comma-separated env var via
        # ``settings.claude_sandbox_excluded_commands_list``.
        if _settings.claude_sandbox_enabled:
            kwargs["sandbox"] = {
                "enabled": True,
                "autoAllowBashIfSandboxed": _settings.claude_sandbox_auto_allow_bash,
                "excludedCommands": _settings.claude_sandbox_excluded_commands_list,
            }
        # Stderr tail capture (PR 05). The SDK lets us subscribe to
        # CLI stderr via a callback; we keep the last
        # ``_STDERR_TAIL_LINES`` lines in a ring buffer so a
        # ``ProcessError`` can surface a useful diagnostic instead
        # of just the exit code.
        kwargs["stderr"] = self._capture_stderr_line
        if mcp_servers:
            kwargs["mcp_servers"] = mcp_servers
            # ``can_use_tool`` is the SDK's per-call permission hook.
            # When the chat router supplies a cross-provider
            # ``permission_check`` (PR 03b), we delegate to it so
            # Claude and Gemini enforce the same policy.  Without
            # one, the bridge falls back to namespace-only approval
            # (the historical behaviour from PR #131).  Either way
            # the whitelist on ``tools=`` is necessary but not
            # sufficient — without ``can_use_tool`` the SDK blocks
            # every custom MCP tool call.
            kwargs["can_use_tool"] = make_can_use_tool(permission_check)
        if self._config.cwd is not None:
            kwargs["cwd"] = self._config.cwd

        env = self._build_env()
        if env:
            kwargs["env"] = env

        # First turn: seed a brand-new SDK session that uses the same UUID
        # as our conversation. Subsequent turns: resume it.  ``force_fresh_session``
        # (PR 05) skips the resume probe so the resume-failure fallback path
        # in :meth:`stream` can re-issue the same conversation as a fresh session.
        if not force_fresh_session and _session_exists(session_id, self._config.cwd):
            kwargs["resume"] = session_id
        else:
            kwargs["session_id"] = session_id

        return ClaudeAgentOptions(**kwargs)

    def _capture_stderr_line(self, line: str) -> None:
        """Push one CLI stderr line onto the rolling diagnostic buffer.

        Called by the SDK on every line the CLI subprocess writes to
        stderr.  Bounded to ``_STDERR_TAIL_LINES`` so a chatty
        subprocess can't grow the buffer without bound.
        """
        buffer = self._stderr_buffer
        buffer.append(line)
        if len(buffer) > _STDERR_TAIL_LINES:
            del buffer[0 : len(buffer) - _STDERR_TAIL_LINES]

    def _build_env(self) -> dict[str, str]:
        """Compose the env dict forwarded to the CLI subprocess."""
        env: dict[str, str] = dict(self._config.extra_env)
        if self._workspace_root:
            token = resolve_api_key(self._workspace_root, "CLAUDE_CODE_OAUTH_TOKEN")
            if token:
                env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        elif self._config.oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self._config.oauth_token
        return env


# ---------------------------------------------------------------------------
# Module-level helpers (also unit-tested directly).
# ---------------------------------------------------------------------------


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


def _claude_display_map(agent_tools: list[AgentTool]) -> dict[str, Any]:
    """Return display metadata keyed by bare and Claude MCP-prefixed names."""
    bare = tool_display_map(agent_tools)
    mapped: dict[str, Any] = dict(bare)
    for name, display in bare.items():
        mapped[claude_tool_id(name)] = display
    return mapped


async def _stream_events_for_attempt(
    *,
    prompt: AsyncIterator[dict[str, Any]],
    options: ClaudeAgentOptions,
    display_by_name: dict[str, Any] | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream ``StreamEvent``s from one ``query()`` call.

    Extracted from :meth:`ClaudeLLM.stream` so the surrounding
    retry/fallback loop stays under the nesting-depth budget (the
    ``while → try → async for → for`` chain in stream() reached
    depth 4, one over the cap). The two loops live here instead.

    Stamps each ``thinking`` event with a monotonically increasing
    ``block_index`` so downstream renderers know where Claude's
    per-block emissions begin and end (#353). Claude already emits one
    ``ThinkingBlock`` per logical block, so an increment-per-event
    counter is the right grain.
    """
    thinking_block_index = 0
    async for message in query(prompt=prompt, options=options):
        for event in _events_from_message(message, display_by_name or {}):
            if event.get("type") == "thinking":
                event["block_index"] = thinking_block_index
                thinking_block_index += 1
            yield event


async def _aiter_user_prompt(
    question: str,
    images: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Wrap a single user message as the streaming-mode input the SDK expects.

    The Claude SDK accepts either a plain string *or* an
    ``AsyncIterable[dict]`` for the ``prompt`` arg, but enforces the
    streaming-mode shape whenever a permission hook (``can_use_tool``)
    is registered — which we now always do via the bridge.  Yielding
    one envelope keeps every call site uniform regardless of whether
    tools were mounted on this turn.

    PR 05: when ``images`` is supplied, the user message becomes a
    multimodal content list (images first, then the text question)
    matching Claude's `messages.content` shape:

        [{"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}},
         {"type": "text", "text": question}]
    """
    if not images:
        yield {
            "type": "user",
            "message": {"role": "user", "content": question},
        }
        return
    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.get("media_type", "image/png"),
                "data": image["data"],
            },
        }
        for image in images
        if "data" in image
    ]
    blocks.append({"type": "text", "text": question})
    yield {
        "type": "user",
        "message": {"role": "user", "content": blocks},
    }


# How many of the most recent rows from ``history`` we surface to the
# model on a cold provider switch. The chat router caps ``history_window``
# to 20 already, but the LCM path can balloon this list — bound it again
# here so a giant history can't poison the first Claude turn.
_HISTORY_PREFIX_MAX_ROWS = 20

# Hard cap on the rendered prefix length. Long histories get truncated
# at the head (oldest first) so the most recent turns are always preserved.
_HISTORY_PREFIX_MAX_CHARS = 12_000


def _render_history_prefix(history: list[dict[str, str]] | None) -> str | None:
    """Render prior turns as a bounded recap the model can read.

    Returns ``None`` when ``history`` is empty or carries no usable
    ``user``/``assistant`` rows. The output is wrapped in clear
    BEGIN/END markers so the model never confuses it with the user's
    actual current message.

    Closes #308.
    """
    if not history:
        return None
    rows = [
        row
        for row in history[-_HISTORY_PREFIX_MAX_ROWS:]
        if row.get("role") in {"user", "assistant"} and (row.get("content") or "").strip()
    ]
    if not rows:
        return None
    lines = ["(Conversation context — earlier turns from this same conversation:)"]
    for row in rows:
        speaker = "User" if row["role"] == "user" else "Assistant"
        content = (row.get("content") or "").strip()
        lines.append(f"{speaker}: {content}")
    body = "\n".join(lines)
    if len(body) > _HISTORY_PREFIX_MAX_CHARS:
        body = "…" + body[-_HISTORY_PREFIX_MAX_CHARS:]
    return f"--- BEGIN PRIOR CONTEXT ---\n{body}\n--- END PRIOR CONTEXT ---"


def _is_retryable_cli_connection(error: BaseException) -> bool:
    """Decide whether a ``CLIConnectionError`` should trigger a retry.

    MCP-related connection errors are NOT retryable — they almost
    always indicate a configuration problem (a bridge server crashed,
    a tool wasn't mounted, …) and retrying just delays the visible
    failure.  Plain network / subprocess hiccups are retryable.
    """
    msg = str(error).lower()
    return "mcp" not in msg


def _retry_backoff_seconds(attempt: int) -> float:
    """Exponential backoff capped at :data:`_RETRY_SLEEP_CEILING_SECONDS`.

    ``attempt`` is 1-indexed (first failure is attempt 1, second is 2…)
    so a base of 1.0 with factor 2.0 produces 1, 2, 4, 8, … seconds.
    """
    base = float(_settings.claude_retry_base_delay_seconds)
    factor = float(_settings.claude_retry_backoff_factor)
    ceiling = float(_settings.claude_retry_max_delay_seconds)
    raw = base * (factor ** max(0, attempt - 1))
    return min(raw, ceiling, _RETRY_SLEEP_CEILING_SECONDS)


def _resolve_sdk_model(model_id: str) -> str:
    """Map frontend model ID to Claude SDK model string.

    Falls back to passing ``model_id`` through unchanged when no explicit
    mapping is registered — the Claude SDK accepts API model IDs directly.
    """
    return _MODEL_MAP.get(model_id, model_id)


def _session_exists(session_id: str, directory: str | None) -> bool:
    """Best-effort probe for an existing Claude SDK transcript.

    A failure to probe (filesystem error, malformed UUID, ...) is treated
    as "no existing session": the next call will pass ``session_id`` and
    the SDK will create a new transcript at that ID. This is the safer
    fallback — passing ``resume`` for a session that doesn't exist would
    be a hard failure.
    """
    try:
        return get_session_info(session_id, directory=directory) is not None
    except Exception as error:
        logger.warning(
            "Probing Claude session %s failed; assuming it does not exist (%s)",
            session_id,
            error,
        )
        return False


# Event-translation helpers live in ``_claude_events`` so this file
# stays under the 500-line gate.  Re-exported here because the existing
# tests + provider code import them from this module — keeping the
# import surface stable means the split is internal-only. Late import is
# intentional: it must follow the class definitions above so the module
# graph round-trips without a circular reference; ruff's E402 doesn't
# express this constraint, so it's silenced explicitly.
from ._claude_events import (  # noqa: E402  (deliberate post-class re-export)
    _error_event,
    _events_from_assistant,
    _events_from_message,
    _tool_result_event,
    _tool_result_to_text,
)

__all__ = [
    "ClaudeLLM",
    "ClaudeLLMConfig",
    "_error_event",
    "_events_from_assistant",
    "_events_from_message",
    "_tool_result_event",
    "_tool_result_to_text",
]
