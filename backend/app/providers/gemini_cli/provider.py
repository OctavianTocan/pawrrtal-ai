"""Gemini CLI provider — drives ``gemini --acp`` over the Agent Client Protocol.

The locally-installed ``gemini`` binary (https://geminicli.com) speaks ACP
(https://agentclientprotocol.com) — the JSON-RPC-over-stdio protocol
Zed / Neovim / JetBrains use to drive coding agents. This module spawns
the subprocess, negotiates the protocol, sends one ``session/prompt`` per
chat turn, and translates streamed ``session/update`` notifications into
Pawrrtal :class:`StreamEvent` records. The CLI is *itself* a fully
agentic loop (its own tool surface, planning, file system access), so we
treat it as a black-box agent the way Claude Code is treated and bypass
Pawrrtal's internal :func:`agent_loop`. History is replayed as a prefix
to the user's message (same fallback pattern :class:`ClaudeLLM` uses
when its transcript is missing); a future revision can switch to ACP's
``session/load`` once we persist the CLI-assigned ``session_id`` per
conversation. Authentication is the user's responsibility — Gemini CLI
reuses whatever Google account / API key / Code Assist license they've
configured on disk; the provider passes no credentials.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import anyio
from acp import connect_to_agent

from app.agents.display import tool_display_map
from app.agents.types import AgentTool, PermissionCheckFn
from app.providers.base import ReasoningEffort, StreamEvent
from app.providers.gemini_cli.acp import (
    AcpFatalError,
    open_session,
    run_prompt_and_drain,
)
from app.providers.gemini_cli.client import PawrrtalAcpClient

if TYPE_CHECKING:
    # Typed connection handle from the ACP Python SDK. Imported under
    # ``TYPE_CHECKING`` to keep the runtime untouched (the SDK warns on
    # constructing ``ClientSideConnection`` directly; we receive one
    # back from ``connect_to_agent``).
    from acp.core import ClientSideConnection

logger = logging.getLogger(__name__)


# Subprocess lifecycle ------------------------------------------------------

# Binary + flag exposed for the startup health-check and tests so the
# magic strings stay in one place.  ``--acp`` is the stable flag; if a
# user reports the CLI rejecting it, the fallback is
# ``--experimental-acp`` — promote this to a setting at that point.
GEMINI_BINARY_NAME = "gemini"
GEMINI_ACP_FLAG = "--acp"

# Wait between ``proc.terminate()`` and the harder ``proc.kill()`` so
# the CLI can flush its transcript before we yank it.
_SHUTDOWN_GRACE_SECONDS = 5.0
# Cleanup cap — by this point we just want descriptors released.
_CONN_CLOSE_TIMEOUT_SECONDS = 2.0

# History prefix caps (mirrors Claude's bounded recap). The chat router
# already caps ``history_window=20`` — the re-cap protects against LCM
# paths that bypass that cap.
_HISTORY_PREFIX_MAX_ROWS = 20
_HISTORY_PREFIX_MAX_CHARS = 12_000


def is_gemini_cli_available() -> bool:
    """Return ``True`` when the ``gemini`` binary is resolvable on ``$PATH``.

    Called once at startup by :func:`backend.main.lifespan` so the
    operator gets a clear ``WARNING`` if the CLI is missing rather than
    a per-request ``error`` event later. Also exported for tests.
    """
    return shutil.which(GEMINI_BINARY_NAME) is not None


class GeminiCliLLM:
    """``AILLM`` backed by ``gemini --acp`` driven via the ACP Python SDK.

    Lifecycle is one subprocess per ``stream()`` call:

    1. Spawn ``gemini --acp --model <slug>`` with the workspace as cwd.
    2. Run ACP ``initialize`` → ``session/new`` → ``session/prompt``.
    3. Stream ``session/update`` notifications via :class:`PawrrtalAcpClient`
       which pushes :class:`StreamEvent` records onto an
       :class:`asyncio.Queue` this method drains.
    4. Tear down the subprocess on success, error, or cancellation.

    Tools, multimodal images, and reasoning effort are accepted for
    :class:`AILLM` protocol parity. Tools are intentionally not bridged
    — the CLI brings its own — and a non-empty list is logged so the
    chat router doesn't silently drop expectations.
    """

    def __init__(self, model_id: str, *, workspace_root: Path | None = None) -> None:
        """Construct the provider.

        Args:
            model_id: Bare model slug (e.g. ``"gemini-2.5-pro"``) the
                CLI accepts as ``--model``. The factory hands us the
                unwrapped ``parsed.model`` so we never see the
                ``gemini-cli:google/`` prefix.
            workspace_root: Absolute workspace path used as cwd for the
                subprocess and as the boundary for filesystem callbacks
                (``fs/read_text_file`` / ``fs/write_text_file``). When
                ``None`` we still let the CLI run but advertise no
                filesystem capability in the ACP handshake — the CLI
                falls back to whatever its own configured tooling can
                do, which for non-chat callers (background utility
                agents) is typically nothing.
        """
        self._model_id = model_id
        self._workspace_root = workspace_root

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
        """Stream one chat turn from the Gemini CLI."""
        logger.debug(
            "GEMINI_CLI_TURN_START conversation_id=%s user_id=%s model=%s",
            conversation_id,
            user_id,
            self._model_id,
        )
        if images:
            logger.debug(
                "GEMINI_CLI_IMAGES_IGNORED conversation_id=%s count=%d",
                conversation_id,
                len(images),
            )
        if tools:
            logger.debug(
                "GEMINI_CLI_TOOLS_IGNORED conversation_id=%s count=%d (CLI brings its own)",
                conversation_id,
                len(tools),
            )
        if reasoning_effort is not None:
            logger.debug(
                "GEMINI_CLI_REASONING_EFFORT_IGNORED value=%s",
                reasoning_effort,
            )

        if not is_gemini_cli_available():
            yield _error_event(
                "Gemini CLI binary not found on PATH. Install with: "
                "npm install -g @google/gemini-cli"
            )
            return

        proc = await _spawn_subprocess(self._model_id, self._workspace_root)
        if proc is None:
            yield _error_event("Failed to spawn Gemini CLI subprocess.")
            return

        try:
            async for event in self._drive_acp_turn(
                proc,
                question=question,
                history=history,
                system_prompt=system_prompt,
                permission_check=permission_check,
                tools=tools,
            ):
                yield event
        finally:
            await _shutdown_subprocess(proc)

    async def _drive_acp_turn(
        self,
        proc: asyncio.subprocess.Process,
        *,
        question: str,
        history: list[dict[str, str]] | None,
        system_prompt: str | None,
        permission_check: PermissionCheckFn | None,
        tools: list[AgentTool] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run one ACP initialize → new_session → prompt cycle on ``proc``.

        Owns the JSON-RPC connection's lifecycle: a single outer
        ``try/finally`` guarantees ``conn.close()`` runs regardless of
        which inner stage (handshake, session, prompt) failed.
        """
        event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()

        display_by_name = tool_display_map(tools) if tools else {}

        client_impl = PawrrtalAcpClient(
            event_queue=event_queue,
            workspace_root=self._workspace_root,
            permission_check=permission_check,
            display_by_name=display_by_name,
        )
        # ``proc.stdin`` / ``proc.stdout`` are typed Optional because
        # ``create_subprocess_exec`` permits PIPE / DEVNULL / FD; we
        # always pass PIPE so the runtime values are non-None.  The
        # ``or _missing_stdio()`` raise narrows the type for downstream
        # callers and surfaces a clear error if the kernel surprises us.
        stdin = proc.stdin or _missing_stdio("stdin")
        stdout = proc.stdout or _missing_stdio("stdout")
        conn = connect_to_agent(client_impl, stdin, stdout)

        try:
            async for event in self._run_handshake_and_prompt(
                conn,
                history=history,
                system_prompt=system_prompt,
                question=question,
                event_queue=event_queue,
            ):
                yield event
        finally:
            try:
                await asyncio.wait_for(conn.close(), timeout=_CONN_CLOSE_TIMEOUT_SECONDS)
            except (TimeoutError, ConnectionError, OSError) as exc:
                logger.warning("GEMINI_CLI_CONN_CLOSE_FAILED reason=%s", exc)

    async def _run_handshake_and_prompt(
        self,
        conn: ClientSideConnection,
        *,
        history: list[dict[str, str]] | None,
        system_prompt: str | None,
        question: str,
        event_queue: asyncio.Queue[StreamEvent | None],
    ) -> AsyncIterator[StreamEvent]:
        """Run handshake + prompt drain. Caller owns ``conn.close()``."""
        try:
            session_id = await open_session(conn, self._workspace_root)
        except AcpFatalError as err:
            yield _error_event(str(err))
            return
        prompt_text = render_history_prefix(history, system_prompt) + question
        async for event in run_prompt_and_drain(
            conn,
            session_id=session_id,
            prompt_text=prompt_text,
            event_queue=event_queue,
        ):
            yield event


# ---------------------------------------------------------------------------
# Subprocess lifecycle helpers.
# ---------------------------------------------------------------------------


async def _spawn_subprocess(
    model_id: str,
    workspace_root: Path | None,
) -> asyncio.subprocess.Process | None:
    """Launch ``gemini --acp`` with the matching model + cwd.

    Returns ``None`` if the subprocess could not be launched (binary
    missing, permission denied, etc.). Callers translate ``None`` into
    a user-visible error event; we keep the function ``None``-returning
    so the caller can decide message phrasing.
    """
    cwd = str(await anyio.Path(workspace_root).resolve()) if workspace_root is not None else None
    cmd = [
        GEMINI_BINARY_NAME,
        GEMINI_ACP_FLAG,
        "--model",
        model_id,
        # ``--skip-trust`` bypasses the CLI's "trust this folder?"
        # interactive prompt, which would otherwise block the JSON-RPC
        # stream on stdin. Safe here because the workspace is per-user
        # under the current process's UID; revisit when running the CLI
        # under a shared service account.
        "--skip-trust",
    ]
    try:
        return await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            # stderr inherits — Gemini's diagnostic lines go to the
            # server's log file alongside our own ``logger.warning``
            # calls. Capturing it into a separate pipe risks a stalled
            # subprocess when nothing drains the pipe.
            stderr=None,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        logger.warning("GEMINI_CLI_SPAWN_FAILED model=%s reason=%s", model_id, exc)
        return None
    except OSError as exc:
        logger.warning("GEMINI_CLI_SPAWN_FAILED model=%s reason=%s", model_id, exc)
        return None


async def _shutdown_subprocess(proc: asyncio.subprocess.Process) -> None:
    """Best-effort shutdown — terminate, wait, escalate to kill.

    Tolerates a race where the subprocess exits between the
    ``returncode`` check and the ``terminate()`` call (the kernel may
    have reaped it already; ``ProcessLookupError`` short-circuits us).
    """
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=_SHUTDOWN_GRACE_SECONDS)
        return
    except TimeoutError:
        pass
    try:
        proc.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=_SHUTDOWN_GRACE_SECONDS)
    except (TimeoutError, ProcessLookupError) as exc:
        logger.warning("GEMINI_CLI_SHUTDOWN_TIMEOUT pid=%s reason=%s", proc.pid, exc)


def _missing_stdio(name: str) -> NoReturn:
    """Raise on missing subprocess stdio pipes — narrows None at call sites.

    Used as ``stdin = proc.stdin or _missing_stdio("stdin")`` so the
    type-checker accepts the narrowing without the helper having to
    fabricate an :class:`asyncio.StreamWriter` from thin air.
    """
    raise RuntimeError(f"Gemini CLI subprocess missing {name} pipe; cannot proceed.")


# ---------------------------------------------------------------------------
# Prompt rendering + small utilities.
# ---------------------------------------------------------------------------


def render_history_prefix(
    history: list[dict[str, str]] | None,
    system_prompt: str | None,
) -> str:
    """Render the system prompt and prior turns as a single text prefix.

    The CLI gets a fresh ACP session per turn, so the only way to carry
    multi-turn context is to fold it into the user prompt. Each section
    is wrapped in clear BEGIN/END markers so the model doesn't confuse
    it with the user's current message; truncation operates on the
    *inner* content (keeping the tail — most-recent turns), then the
    wrappers are applied, so the markers are never lost no matter how
    long the input.

    Returns an empty string when there's nothing to prefix, so the
    caller can ``render_history_prefix(...) + question`` unconditionally.
    """
    sections: list[str] = []
    sp = (system_prompt or "").strip()
    if sp:
        sections.append(_wrap_section("SYSTEM CONTEXT", _truncate_tail(sp)))
    rendered_history = _render_history_lines(history)
    if rendered_history:
        sections.append(
            _wrap_section("PRIOR CONVERSATION", _truncate_tail(rendered_history)),
        )
    return "\n".join(sections)


def _wrap_section(label: str, body: str) -> str:
    """Wrap ``body`` in ``--- BEGIN <label> --- / --- END <label> ---`` markers."""
    return f"--- BEGIN {label} ---\n{body}\n--- END {label} ---\n"


def _truncate_tail(text: str) -> str:
    """Cap ``text`` at :data:`_HISTORY_PREFIX_MAX_CHARS`, keeping the tail.

    Tail preservation is the right call for both system prompts and
    history: the most recent rows / instructions are what the model
    needs to see if anything is dropped.
    """
    if len(text) <= _HISTORY_PREFIX_MAX_CHARS:
        return text
    return "…" + text[-_HISTORY_PREFIX_MAX_CHARS:]


def _render_history_lines(history: list[dict[str, str]] | None) -> str:
    """Render the trailing window of history rows as ``Speaker: text`` lines.

    Returns the empty string when history is missing or carries no
    usable ``user`` / ``assistant`` rows.
    """
    if not history:
        return ""
    rows = [
        row
        for row in history[-_HISTORY_PREFIX_MAX_ROWS:]
        if row.get("role") in {"user", "assistant"} and (row.get("content") or "").strip()
    ]
    if not rows:
        return ""
    lines: list[str] = []
    for row in rows:
        speaker = "User" if row["role"] == "user" else "Assistant"
        content = (row.get("content") or "").strip()
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _error_event(message: str) -> StreamEvent:
    """Build the ``StreamEvent(type="error")`` shape the SSE encoder consumes."""
    return StreamEvent(type="error", content=message)


__all__ = [
    "GEMINI_ACP_FLAG",
    "GEMINI_BINARY_NAME",
    "GeminiCliLLM",
    "is_gemini_cli_available",
    "render_history_prefix",
]
