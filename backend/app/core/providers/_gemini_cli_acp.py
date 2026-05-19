"""ACP protocol drive for the Gemini CLI provider.

Split out of :mod:`gemini_cli_provider` to keep that module under the
500-line gate. Owns the JSON-RPC handshake (``initialize`` +
``session/new``), the prompt-and-drain loop, and the cancellation
cleanup. Subprocess lifecycle, history rendering, and the public
:class:`GeminiCliLLM` class stay in the provider module.

Connection close lifecycle: :func:`run_prompt_and_drain` *does not*
call ``conn.close()`` — the caller (``_drive_acp_turn``) owns a single
outer ``try/finally`` that closes the connection regardless of which
inner stage failed, so a failed handshake never leaks dispatcher tasks.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from acp import PROTOCOL_VERSION, RequestError, text_block
from acp.schema import ClientCapabilities, FileSystemCapabilities

from .base import StreamEvent

if TYPE_CHECKING:
    from acp.core import ClientSideConnection

logger = logging.getLogger(__name__)


_INIT_TIMEOUT_SECONDS = 30.0
"""Cap on the ACP ``initialize`` handshake."""

_NEW_SESSION_TIMEOUT_SECONDS = 30.0
"""Cap on ``session/new``."""

_CANCEL_TIMEOUT_SECONDS = 2.0
"""Cap on the in-flight ``session/cancel`` notification."""


class AcpFatalError(Exception):
    """Internal signal for "initialize or new_session failed".

    Raised inside :func:`open_session`, caught at the top of the
    surrounding handshake driver so the public ``stream`` contract
    surfaces a single ``error`` event rather than an unhandled
    exception. ``str(err)`` carries the user-facing message via
    ``Exception.args[0]``.
    """


async def open_session(conn: ClientSideConnection, workspace_root: Path | None) -> str:
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
        raise AcpFatalError(
            f"Gemini CLI did not respond to ACP initialize within {_INIT_TIMEOUT_SECONDS:.0f}s.",
        ) from exc
    except RequestError as exc:
        raise AcpFatalError(f"Gemini CLI ACP initialize failed: {exc}") from exc

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
        raise AcpFatalError(
            f"Gemini CLI did not respond to session/new within {_NEW_SESSION_TIMEOUT_SECONDS:.0f}s.",
        ) from exc
    except RequestError as exc:
        raise AcpFatalError(f"Gemini CLI session/new failed: {exc}") from exc

    return session.session_id


async def run_prompt_and_drain(
    conn: ClientSideConnection,
    *,
    session_id: str,
    prompt_text: str,
    event_queue: asyncio.Queue[StreamEvent | None],
) -> AsyncIterator[StreamEvent]:
    """Send the prompt and drain queued events until the turn ends."""
    prompt_outcome: dict[str, Any] = {}
    prompt_task = asyncio.create_task(
        _run_prompt(conn, session_id, prompt_text, prompt_outcome, event_queue),
    )
    try:
        async for event in _drain_queue(event_queue):
            yield event
        await prompt_task
        error_text = prompt_outcome.get("error")
        if error_text is not None:
            yield StreamEvent(type="error", content=error_text)
        else:
            response = prompt_outcome.get("response")
            stop_reason = getattr(response, "stop_reason", None)
            logger.info("GEMINI_CLI_TURN_DONE stop_reason=%s", stop_reason)
    except asyncio.CancelledError:
        await _cancel_turn(conn, session_id, prompt_task)
        raise


async def _run_prompt(
    conn: ClientSideConnection,
    session_id: str,
    prompt_text: str,
    prompt_outcome: dict[str, Any],
    event_queue: asyncio.Queue[StreamEvent | None],
) -> None:
    """Send ``session/prompt`` and record the outcome.

    The final ``except Exception`` is the deliberate boundary between
    the SDK and the user-facing SSE stream: unknown failures must
    surface as a clean error event rather than propagate raw and crash
    the chat surface mid-turn.
    """
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
    except Exception as exc:
        # Last-resort boundary between the SDK and the SSE stream —
        # unknown failures must surface as a clean error event, not
        # propagate raw and crash the chat surface mid-turn.
        logger.exception("GEMINI_CLI_PROMPT_UNEXPECTED")
        prompt_outcome["error"] = f"Gemini CLI prompt failed unexpectedly: {exc}"
    finally:
        await event_queue.put(None)


async def _cancel_turn(
    conn: ClientSideConnection,
    session_id: str,
    prompt_task: asyncio.Task[None],
) -> None:
    """Politely cancel an in-flight ACP turn after the caller aborted.

    Narrow ``except`` clauses + WARNING logs so a buggy cancel call
    (transport gone, SDK signature drift) shows up in operator logs
    instead of being silently swallowed.
    """
    try:
        await asyncio.wait_for(
            conn.cancel(session_id=session_id),
            timeout=_CANCEL_TIMEOUT_SECONDS,
        )
    except (TimeoutError, ConnectionError, OSError, RequestError) as exc:
        logger.warning("GEMINI_CLI_CANCEL_FAILED reason=%s", exc)
    prompt_task.cancel()
    try:
        await prompt_task
    except asyncio.CancelledError:
        pass
    except (RequestError, TimeoutError, ConnectionError, OSError) as exc:
        logger.warning("GEMINI_CLI_PROMPT_TASK_ERR_DURING_CANCEL reason=%s", exc)


async def _drain_queue(
    event_queue: asyncio.Queue[StreamEvent | None],
) -> AsyncIterator[StreamEvent]:
    """Yield queued events until the producer signals end-of-turn with ``None``."""
    while True:
        event = await event_queue.get()
        if event is None:
            return
        yield event
