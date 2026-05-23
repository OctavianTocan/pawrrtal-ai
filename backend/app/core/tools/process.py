"""Background process management tool.

Provides start/list/poll/log/wait/kill/write/submit/close actions for
background processes.  Registry is module-level with conversation-scoped
ownership checks.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.tools.display import make_tool_display

log = logging.getLogger(__name__)

_MAX_OUTPUT_BUFFER_BYTES = 200_000
_WAIT_TIMEOUT_SECONDS = 30

_VALID_ACTIONS = frozenset({
    "start", "list", "poll", "log", "wait", "kill", "write", "submit", "close",
})


@dataclass
class ManagedProcess:
    """A background process tracked by the registry."""

    pid: str
    conversation_id: str
    command: str
    process: asyncio.subprocess.Process
    output: deque[str] = field(default_factory=deque)
    reader_task: asyncio.Task[None] | None = None
    total_bytes: int = 0


_registry: dict[str, ManagedProcess] = {}
_lock = asyncio.Lock()


def _get_process(
    pid: str, conversation_id: str
) -> ManagedProcess | None:
    """Look up a process, enforcing conversation ownership."""
    entry = _registry.get(pid)
    if entry is None or entry.conversation_id != conversation_id:
        return None
    return entry


def _result(
    *, success: bool, **extra: Any
) -> str:
    return json.dumps({"success": success, **extra})


async def _reader_loop(entry: ManagedProcess) -> None:
    """Read stdout into the rolling output buffer."""
    stream = entry.process.stdout
    if stream is None:
        return
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        text = chunk.decode("utf-8", errors="replace")
        entry.output.append(text)
        entry.total_bytes += len(text)
        while entry.total_bytes > _MAX_OUTPUT_BUFFER_BYTES and entry.output:
            removed = entry.output.popleft()
            entry.total_bytes -= len(removed)


def make_process_tool(
    *, workspace_root: Path, conversation_id: str
) -> AgentTool:
    """Return the ``process`` AgentTool scoped to *workspace_root*."""
    root = Path(workspace_root).resolve()

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        if action not in _VALID_ACTIONS:
            return _result(success=False, error=f"Unknown action: {action!r}")
        if action == "start":
            return await _handle_start(root, conversation_id, kwargs)
        if action == "list":
            return _handle_list(conversation_id)
        return await _dispatch_pid_action(action, kwargs, conversation_id)

    return AgentTool(
        name="process",
        description=(
            "Manage background processes. Actions: start, list, poll, log, "
            "wait, kill, write, submit, close."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(_VALID_ACTIONS),
                    "description": "The operation to perform.",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to start (only for 'start').",
                },
                "pid": {
                    "type": "string",
                    "description": "Process ID (required for all actions except start/list).",
                },
                "input": {
                    "type": "string",
                    "description": "Text to write to stdin (only for 'write').",
                },
            },
            "required": ["action"],
        },
        execute=execute,
        display=make_tool_display(
            icon="⚙️",
            label="Process",
            present=lambda args: f"⚙️ process({args.get('action', '')})",
            compact=lambda args: f"process({args.get('action', '')})",
        ),
    )


async def _dispatch_pid_action(
    action: str, kwargs: dict[str, Any], conversation_id: str
) -> str:
    """Resolve pid, check ownership, and dispatch to the right handler."""
    pid = kwargs.get("pid", "")
    if not pid:
        return _result(success=False, error="'pid' is required.")
    entry = _get_process(pid, conversation_id)
    if entry is None:
        return _result(success=False, error=f"No process with pid={pid!r}")

    dispatch: dict[str, Any] = {
        "poll": lambda: _handle_poll(entry),
        "log": lambda: _handle_log(entry),
        "wait": lambda: _handle_wait(entry),
        "kill": lambda: _handle_kill(entry),
        "write": lambda: _handle_write(entry, kwargs),
        "submit": lambda: _handle_submit(entry),
        "close": lambda: _handle_close(entry),
    }
    result = dispatch[action]()
    if asyncio.iscoroutine(result):
        return await result
    return result


async def _handle_start(
    root: Path, conversation_id: str, kwargs: dict[str, Any]
) -> str:
    command = kwargs.get("command", "")
    if not command:
        return _result(success=False, error="'command' is required for start.")

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.PIPE,
        cwd=str(root),
        preexec_fn=os.setsid,
    )
    pid = str(uuid.uuid4())[:8]
    entry = ManagedProcess(
        pid=pid,
        conversation_id=conversation_id,
        command=command,
        process=proc,
    )
    entry.reader_task = asyncio.create_task(_reader_loop(entry))
    async with _lock:
        _registry[pid] = entry

    return _result(success=True, pid=pid)


def _handle_list(conversation_id: str) -> str:
    processes = []
    for entry in _registry.values():
        if entry.conversation_id != conversation_id:
            continue
        running = entry.process.returncode is None
        processes.append({
            "pid": entry.pid,
            "command": entry.command,
            "running": running,
        })
    return json.dumps({"success": True, "processes": processes})


def _handle_poll(entry: ManagedProcess) -> str:
    output = "".join(entry.output)
    return _result(success=True, output=output)


def _handle_log(entry: ManagedProcess) -> str:
    output = "".join(entry.output)
    return _result(success=True, output=output)


async def _handle_wait(entry: ManagedProcess) -> str:
    try:
        code = await asyncio.wait_for(
            entry.process.wait(), timeout=_WAIT_TIMEOUT_SECONDS
        )
    except TimeoutError:
        return _result(
            success=False,
            error=f"Process did not exit within {_WAIT_TIMEOUT_SECONDS}s.",
        )
    if entry.reader_task is not None:
        await entry.reader_task
    return _result(success=True, exit_code=code)


async def _handle_kill(entry: ManagedProcess) -> str:
    if entry.process.returncode is not None:
        return _result(success=True, exit_code=entry.process.returncode)
    try:
        pgid = os.getpgid(entry.process.pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        await asyncio.wait_for(entry.process.wait(), timeout=5)
    except TimeoutError:
        entry.process.kill()
    return _result(success=True)


async def _handle_write(
    entry: ManagedProcess, kwargs: dict[str, Any]
) -> str:
    stdin_data = kwargs.get("input", "")
    if entry.process.stdin is None:
        return _result(success=False, error="Process stdin not available.")
    entry.process.stdin.write(stdin_data.encode("utf-8"))
    await entry.process.stdin.drain()
    return _result(success=True)


async def _handle_submit(entry: ManagedProcess) -> str:
    if entry.process.stdin is None:
        return _result(success=False, error="Process stdin not available.")
    entry.process.stdin.close()
    return _result(success=True)


async def _handle_close(entry: ManagedProcess) -> str:
    if entry.process.returncode is None:
        await _handle_kill(entry)
    if entry.reader_task is not None and not entry.reader_task.done():
        entry.reader_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry.reader_task
    async with _lock:
        _registry.pop(entry.pid, None)
    return _result(success=True)
