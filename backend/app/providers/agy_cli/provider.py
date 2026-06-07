"""Antigravity ``agy`` CLI provider.

This provider treats ``agy`` as a black-box local coding agent.  The CLI
does not expose ACP today, so we drive non-interactive print mode and
parse stdout/log files conservatively.

Security note: ``agy`` permission behavior is governed by the user's
global Antigravity CLI settings. In local probes, ``--sandbox`` did not
enforce a strict ``--add-dir`` workspace boundary when
``toolPermission`` was ``always-proceed``. Do not present this provider
as Pawrrtal-enforced tool approval until ask-mode has been tested and
integrated.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from app.agents.types import AgentTool
from app.provider_sessions import ProviderSessionTurnState, load_provider_session
from app.providers._stream_logging import log_provider_stream_event
from app.providers.base import ReasoningEffort, StreamEvent

from .command import DEFAULT_PRINT_TIMEOUT, build_agy_command, is_agy_cli_available
from .logs import classify_log_line
from .output import build_framed_prompt, extract_final_answer, is_timeout_output
from .session import parse_conversation_id

logger = logging.getLogger(__name__)
PROVIDER_SESSION_KIND = "agy_cli"


class AgyCliLLM:
    """``AILLM`` backed by local ``agy --print`` subprocess turns."""

    def __init__(self, model_id: str, *, workspace_root: Path | None = None) -> None:
        self._model_id = model_id
        self._workspace_root = workspace_root
        self._session_by_conversation: dict[uuid.UUID, str] = {}

    async def prepare_turn_session(
        self,
        *,
        conversation_id: uuid.UUID,
        workspace_root: Path | None,
        model_id: str | None,
        tools: list[AgentTool] | None,
        reasoning_effort: ReasoningEffort | None,
        question: str,
    ) -> ProviderSessionTurnState:
        """Prepare generic session continuity for the turn runner."""
        del workspace_root, model_id, tools, reasoning_effort, question
        record = await load_provider_session(conversation_id)
        if record is None or record.kind != PROVIDER_SESSION_KIND or not record.session_id:
            self._session_by_conversation.pop(conversation_id, None)
            return ProviderSessionTurnState(kind=PROVIDER_SESSION_KIND)
        return ProviderSessionTurnState(
            kind=PROVIDER_SESSION_KIND,
            session_id=record.session_id,
            stream_kwargs={"agy_conversation_id": record.session_id},
            omit_history=True,
        )

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        history: list[dict[str, str]] | None = None,
        tools: list[AgentTool] | None = None,
        system_prompt: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        images: list[dict[str, str]] | None = None,
        agy_conversation_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream one Antigravity CLI turn."""
        del user_id
        if tools:
            logger.debug("AGY_CLI_TOOLS_IGNORED count=%d", len(tools))
        if reasoning_effort is not None:
            logger.debug("AGY_CLI_REASONING_EFFORT_IGNORED value=%s", reasoning_effort)
        if images:
            logger.debug("AGY_CLI_IMAGES_IGNORED count=%d", len(images))

        if not is_agy_cli_available():
            yield _error_event("Antigravity agy CLI binary not found on PATH.")
            return

        workspace_roots = _workspace_roots(self._workspace_root)
        log_file = _make_log_file(conversation_id)
        prompt = build_framed_prompt(
            question=question,
            history=history,
            system_prompt=system_prompt,
        )
        command = build_agy_command(
            workspace_roots=workspace_roots,
            log_file=log_file,
            prompt=prompt,
            timeout=DEFAULT_PRINT_TIMEOUT,
            conversation_id=agy_conversation_id
            or self._session_by_conversation.get(conversation_id),
        )

        proc = await _spawn(command, cwd=workspace_roots[0] if workspace_roots else None)
        if proc is None:
            yield _error_event("Failed to spawn Antigravity agy CLI subprocess.")
            return

        try:
            stdout = await _communicate(proc)
        except asyncio.CancelledError:
            await _shutdown_process(proc)
            logger.info(
                "AGY_CLI_CANCELLED conversation_id=%s model=%s", conversation_id, self._model_id
            )
            raise

        remembered_id = self._remember_session(conversation_id, log_file)
        _log_agy_events(log_file, conversation_id, self._model_id)

        if is_timeout_output(stdout):
            yield _error_event("Antigravity CLI timed out waiting for a response.")
            return

        answer = extract_final_answer(stdout)
        if answer is None:
            logger.warning("AGY_CLI_FINAL_MARKER_MISSING stdout=%r", stdout[-500:])
            yield _error_event("Antigravity CLI returned an unframed response.")
            return

        if remembered_id and remembered_id != agy_conversation_id:
            yield StreamEvent(
                type="internal",
                kind="provider_session_created",
                provider="agy_cli",
                session_id=remembered_id,
            )
        yield StreamEvent(type="delta", content=answer)

    def _remember_session(self, conversation_id: uuid.UUID, log_file: Path) -> str | None:
        try:
            log_text = log_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("AGY_CLI_LOG_READ_FAILED path=%s reason=%s", log_file, exc)
            return None
        agy_conversation_id = parse_conversation_id(log_text)
        if agy_conversation_id:
            self._session_by_conversation[conversation_id] = agy_conversation_id
        return agy_conversation_id


def _workspace_roots(workspace_root: Path | None) -> list[Path]:
    if workspace_root is None:
        return []
    return [workspace_root.resolve()]


def _make_log_file(conversation_id: uuid.UUID) -> Path:
    base = Path(tempfile.gettempdir()) / "pawrrtal-agy-cli"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{conversation_id}.log"


async def _spawn(
    command: list[str],
    *,
    cwd: Path | None,
) -> asyncio.subprocess.Process | None:
    try:
        return await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd is not None else None,
        )
    except (FileNotFoundError, OSError) as exc:
        logger.warning("AGY_CLI_SPAWN_FAILED reason=%s", exc)
        return None


async def _communicate(proc: asyncio.subprocess.Process) -> str:
    stdout, stderr = await proc.communicate()
    if stderr:
        logger.debug("AGY_CLI_STDERR %s", stderr.decode(errors="replace")[-1000:])
    return stdout.decode(errors="replace")


async def _shutdown_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        return
    except TimeoutError:
        pass
    try:
        proc.kill()
    except ProcessLookupError:
        return
    await proc.wait()


def _log_agy_events(log_file: Path, conversation_id: uuid.UUID, model_id: str) -> None:
    try:
        lines = log_file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("AGY_CLI_LOG_READ_FAILED path=%s reason=%s", log_file, exc)
        return
    for line in lines:
        event = classify_log_line(line)
        if event is None:
            continue
        log_provider_stream_event(
            logger,
            provider="agy-cli",
            model=model_id,
            conversation_id=conversation_id,
            event={"type": event["event"], "content": event["summary"]},
        )


def _error_event(message: str) -> StreamEvent:
    return StreamEvent(type="error", content=message)
