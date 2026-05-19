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
import contextlib
import logging
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from acp import PROTOCOL_VERSION, RequestError, connect_to_agent, text_block
from acp.schema import ClientCapabilities, FileSystemCapabilities

from app.core.agent_loop.types import AgentTool, PermissionCheckFn

from ._gemini_cli_client import PawrrtalAcpClient
from .base import ReasoningEffort, StreamEvent

logger = logging.getLogger(__name__)


# Subprocess lifecycle ------------------------------------------------------

# Binary + flag exposed for the startup health-check and tests so the
# magic strings stay in one place.  ``--acp`` is the stable flag from
# Gemini CLI ``0.21+``; older builds use ``--experimental-acp`` and
# need to lift this to a setting.
GEMINI_BINARY_NAME = "gemini"
GEMINI_ACP_FLAG = "--acp"

# Timeouts: handshakes finish in under a second when the CLI is live;
# the caps below treat anything past them as a wedged subprocess.
_INIT_TIMEOUT_SECONDS = 30.0
_NEW_SESSION_TIMEOUT_SECONDS = 30.0
# Wait between ``proc.terminate()`` and the harder ``proc.kill()`` so
# the CLI can flush its transcript before we yank it.
_SHUTDOWN_GRACE_SECONDS = 5.0
# Cleanup-path caps — by this point we just want descriptors released
# and ``session/cancel`` flushed to the kernel buffer.
_CONN_CLOSE_TIMEOUT_SECONDS = 2.0
_CANCEL_TIMEOUT_SECONDS = 2.0

# History rendering — mirrors ``ClaudeLLM._HISTORY_PREFIX_MAX_ROWS``
# / ``_HISTORY_PREFIX_MAX_CHARS``.  The chat router caps ``history_window``
# to 20 already; we re-cap so the LCM path can't balloon the prefix.
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
    ) -> AsyncIterator[StreamEvent]:
        """Run one ACP initialize → new_session → prompt cycle on ``proc``."""
        event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        client_impl = PawrrtalAcpClient(
            event_queue=event_queue,
            workspace_root=self._workspace_root,
            permission_check=permission_check,
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
            session_id = await _open_session(conn, self._workspace_root)
        except _AcpFatalError as err:
            yield _error_event(err.message)
            return

        prompt_text = render_history_prefix(history, system_prompt) + question
        async for event in _run_prompt_and_drain(
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
    cwd = str(workspace_root) if workspace_root is not None else None
    cmd = [
        GEMINI_BINARY_NAME,
        GEMINI_ACP_FLAG,
        "--model",
        model_id,
        # The Gemini CLI may otherwise refuse to operate in a directory
        # it hasn't been told to trust. The workspace is owned by the
        # current user; trust is fine.
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
    """Best-effort shutdown — terminate, wait, escalate to kill."""
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=_SHUTDOWN_GRACE_SECONDS)
        return
    except TimeoutError:
        pass
    proc.kill()
    with contextlib.suppress(asyncio.TimeoutError, ProcessLookupError):
        await asyncio.wait_for(proc.wait(), timeout=_SHUTDOWN_GRACE_SECONDS)


def _missing_stdio(name: str) -> Any:
    """Raise on missing subprocess stdio pipes — narrows None at call sites.

    Used as ``stdin = proc.stdin or _missing_stdio("stdin")`` so the
    type-checker accepts the narrowing without the helper having to
    fabricate an :class:`asyncio.StreamWriter` from thin air. Return
    type is ``Any`` for the same reason: this function never returns.
    """
    raise RuntimeError(f"Gemini CLI subprocess missing {name} pipe; cannot proceed.")


# ---------------------------------------------------------------------------
# ACP handshake + prompt drive.
# ---------------------------------------------------------------------------


class _AcpFatalError(Exception):
    """Internal signal for "initialize or new_session failed".

    Raised inside the ACP drive helpers, caught at the top of
    :meth:`GeminiCliLLM._drive_acp_turn` so the public ``stream``
    contract surfaces a single ``error`` event rather than an
    unhandled exception.
    """

    def __init__(self, message: str) -> None:
        """Carry the user-facing error message verbatim."""
        super().__init__(message)
        self.message = message


async def _open_session(conn: Any, workspace_root: Path | None) -> str:
    """Run ``initialize`` + ``session/new`` and return the session id."""
    fs_capable = workspace_root is not None
    capabilities = ClientCapabilities(
        fs=FileSystemCapabilities(
            read_text_file=fs_capable,
            write_text_file=fs_capable,
        ),
        terminal=False,
    )
    try:
        init_resp = await asyncio.wait_for(
            conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=capabilities,
            ),
            timeout=_INIT_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise _AcpFatalError("Gemini CLI did not respond to ACP initialize within 30s.") from exc
    except RequestError as exc:
        raise _AcpFatalError(f"Gemini CLI ACP initialize failed: {exc}") from exc

    logger.info(
        "GEMINI_CLI_INITIALIZED protocol_version=%s",
        getattr(init_resp, "protocol_version", "?"),
    )

    cwd = str(workspace_root) if workspace_root is not None else str(Path.cwd())
    try:
        session = await asyncio.wait_for(
            conn.new_session(cwd=cwd, mcp_servers=[]),
            timeout=_NEW_SESSION_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise _AcpFatalError("Gemini CLI did not respond to session/new within 30s.") from exc
    except RequestError as exc:
        raise _AcpFatalError(f"Gemini CLI session/new failed: {exc}") from exc

    return session.session_id


async def _run_prompt_and_drain(
    conn: Any,
    *,
    session_id: str,
    prompt_text: str,
    event_queue: asyncio.Queue[StreamEvent | None],
) -> AsyncIterator[StreamEvent]:
    """Send the prompt and drain queued events until the turn ends."""
    prompt_outcome: dict[str, Any] = {}

    async def run_prompt() -> None:
        try:
            response = await conn.prompt(
                session_id=session_id,
                prompt=[text_block(prompt_text)],
            )
            prompt_outcome["response"] = response
        except RequestError as exc:
            prompt_outcome["error"] = f"Gemini CLI ACP prompt failed: {exc}"
        except (TimeoutError, ConnectionError, OSError) as exc:
            prompt_outcome["error"] = f"Gemini CLI ACP transport error: {exc}"
        finally:
            await event_queue.put(None)

    prompt_task = asyncio.create_task(run_prompt())
    try:
        async for event in _drain_queue(event_queue):
            yield event
        await prompt_task
        error_text = prompt_outcome.get("error")
        if error_text is not None:
            yield _error_event(error_text)
        else:
            response = prompt_outcome.get("response")
            stop_reason = getattr(response, "stop_reason", None)
            logger.info("GEMINI_CLI_TURN_DONE stop_reason=%s", stop_reason)
    except asyncio.CancelledError:
        # Caller aborted the SSE stream — politely tell the CLI to
        # stop and re-raise so the surrounding ``finally`` blocks in
        # :meth:`GeminiCliLLM.stream` clean up the subprocess.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                conn.cancel(session_id=session_id),
                timeout=_CANCEL_TIMEOUT_SECONDS,
            )
        prompt_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await prompt_task
        raise
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(conn.close(), timeout=_CONN_CLOSE_TIMEOUT_SECONDS)


async def _drain_queue(
    event_queue: asyncio.Queue[StreamEvent | None],
) -> AsyncIterator[StreamEvent]:
    """Yield queued events until the producer signals end-of-turn with ``None``."""
    while True:
        event = await event_queue.get()
        if event is None:
            return
        yield event


# ---------------------------------------------------------------------------
# Prompt rendering + small utilities.
# ---------------------------------------------------------------------------


def render_history_prefix(
    history: list[dict[str, str]] | None,
    system_prompt: str | None,
) -> str:
    """Render the system prompt and prior turns as a single text prefix.

    The CLI gets a fresh ACP session per turn, so the only way to carry
    multi-turn context is to fold it into the user prompt. The prefix is
    wrapped in clear BEGIN/END markers so the model doesn't confuse it
    with the user's current message — same pattern :class:`ClaudeLLM`
    uses for its provider-switch fallback.

    Returns an empty string when there's nothing to prefix, so the caller
    can ``render_history_prefix(...) + question`` unconditionally.
    """
    parts: list[str] = []
    sp = (system_prompt or "").strip()
    if sp:
        parts.append("--- BEGIN SYSTEM CONTEXT ---")
        parts.append(sp)
        parts.append("--- END SYSTEM CONTEXT ---")
        parts.append("")
    rendered_history = _render_history_lines(history)
    if rendered_history:
        parts.append("--- BEGIN PRIOR CONVERSATION ---")
        parts.append(rendered_history)
        parts.append("--- END PRIOR CONVERSATION ---")
        parts.append("")
    body = "\n".join(parts)
    if len(body) > _HISTORY_PREFIX_MAX_CHARS:
        body = "…" + body[-_HISTORY_PREFIX_MAX_CHARS:]
    return body


def _render_history_lines(history: list[dict[str, str]] | None) -> str:
    """Render the trailing window of history rows as ``Speaker: text`` lines.

    Returns the empty string when history is missing or carries no
    usable ``user``/``assistant`` rows. Extracted so
    :func:`render_history_prefix` stays under the nesting budget.
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
