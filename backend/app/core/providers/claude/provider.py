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

Helpers that used to live in this file have been split into sibling
modules so this file stays under the project's 500-line budget:

- :mod:`.events` — Claude SDK ``Message`` → ``StreamEvent`` projection.
- :mod:`.tool_bridge` — cross-provider ``AgentTool`` → in-process MCP server.
- :mod:`.tools` — per-request whitelist + display-map composition.
- :mod:`.prompt` — multimodal ``aiter_user_prompt`` envelope assembly.
- :mod:`.history` — bounded prior-turn recap for cross-provider switches.
- :mod:`.retry` — transient-error classification + backoff.

All public names (including the underscore-prefixed test helpers) are
re-exported from :mod:`app.core.providers.claude` (the package
``__init__.py``) so existing import sites keep working.
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

from app.core.agent_loop.display import ToolDisplay
from app.core.agent_loop.types import AgentTool, PermissionCheckFn
from app.core.agent_system_prompt import (
    DEFAULT_AGENT_SYSTEM_PROMPT as _DEFAULT_SYSTEM_PROMPT,
)
from app.core.config import settings as _settings
from app.core.providers.base import ReasoningEffort, StreamEvent
from app.core.providers.claude.events import _error_event, _events_from_message
from app.core.providers.claude.history import _render_history_prefix
from app.core.providers.claude.options import build_options
from app.core.providers.claude.prompt import _aiter_user_prompt
from app.core.providers.claude.retry import (
    _is_retryable_cli_connection,
    _retry_backoff_seconds,
)
from app.core.providers.claude.tools import _claude_display_map

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

# Single-turn chat default; widened to ``_TOOL_ENABLED_MAX_TURNS`` by
# :func:`app.core.providers.claude.options.build_options` when tool use
# is enabled. Mirrored in :mod:`.options` so this module doesn't need
# to import from there for a single int.
_DEFAULT_MAX_TURNS = 1

# With ``tools=[]`` no tool ever runs, so the choice here is mostly
# cosmetic. We pick "default" rather than "bypassPermissions" so that
# enabling a tool in the future fails closed instead of open.
_DEFAULT_PERMISSION_MODE: PermissionMode = "default"

# Last N CLI stderr lines kept in the rolling buffer for diagnostics
# on a ``ProcessError``.  Bounded so a chatty subprocess can't grow
# the buffer without bound.
_STDERR_TAIL_LINES = 20

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
                by :mod:`.tool_bridge` so the SDK can call them.
            system_prompt: Optional system prompt to override the
                provider-default chat-scoped prompt. Falls back to
                :data:`DEFAULT_AGENT_SYSTEM_PROMPT` when ``None``.
            reasoning_effort: Optional reasoning-depth knob. Forwarded to
                Claude Code as ``effort`` when set.
            permission_check: Optional cross-provider ``can_use_tool``
                gate (PR 03b).  Bound into the Claude SDK's
                ``can_use_tool`` callback via
                :func:`.tool_bridge.make_can_use_tool` so the
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
            options = build_options(
                config=self._config,
                workspace_root=self._workspace_root,
                conversation_id=conversation_id,
                sdk_model=_resolve_sdk_model(self._model_id),
                stderr_callback=self._capture_stderr_line,
                session_probe=_session_exists,
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


# ---------------------------------------------------------------------------
# Module-level helpers (provider-internal — also unit-tested directly).
# ---------------------------------------------------------------------------


async def _stream_events_for_attempt(
    *,
    prompt: AsyncIterator[dict[str, Any]],
    options: ClaudeAgentOptions,
    display_by_name: dict[str, ToolDisplay] | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream ``StreamEvent``s from one ``query()`` call.

    Extracted from :meth:`ClaudeLLM.stream` so the surrounding
    retry/fallback loop stays under the nesting-depth budget (the
    ``while → try → async for → for`` chain in stream() reached
    depth 4, one over the cap). The two loops live here instead.
    """
    async for message in query(prompt=prompt, options=options):
        for event in _events_from_message(message, display_by_name or {}):
            yield event


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
