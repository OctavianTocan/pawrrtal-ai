"""Foreground shell tool with cwd tracking and output truncation.

Runs commands via ``asyncio.create_subprocess_shell`` rooted at the
workspace directory.  Tracks cwd per conversation using a sentinel
marker so ``cd`` persists across calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.governance.bash_boundary import check_bash_directory_boundary
from app.core.tools.display import make_tool_display

log = logging.getLogger(__name__)

_CWD_SENTINEL = "__PAWRRTAL_CWD__"
_MAX_OUTPUT_CHARS = 50_000
_HEAD_RATIO = 0.4
_TIMEOUT_SECONDS = 120
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

_conversation_cwd: dict[str, Path] = {}


def make_terminal_tool(
    *, workspace_root: Path, conversation_id: str
) -> AgentTool:
    """Return the ``terminal`` AgentTool scoped to *workspace_root*."""
    root = Path(workspace_root).resolve()

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        if not command:
            return json.dumps({"exit_code": 1, "error": "'command' is required."})

        cwd = _conversation_cwd.get(conversation_id, root)

        allowed, reason = check_bash_directory_boundary(command, cwd, root)
        if not allowed:
            return json.dumps({"exit_code": 1, "error": f"Denied: {reason}"})

        wrapped = (
            f"{command}; __EC=$?; "
            f"printf '\\n{_CWD_SENTINEL}\\n'; pwd; exit $__EC"
        )

        try:
            proc = await asyncio.create_subprocess_shell(
                wrapped,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(cwd),
            )
            raw_output, _ = await asyncio.wait_for(
                proc.communicate(), timeout=_TIMEOUT_SECONDS
            )
        except TimeoutError:
            return json.dumps({
                "exit_code": 124,
                "error": f"Command timed out after {_TIMEOUT_SECONDS}s.",
            })

        decoded = raw_output.decode("utf-8", errors="replace")
        decoded = _ANSI_RE.sub("", decoded)

        output, new_cwd = _extract_cwd(decoded)
        if new_cwd is not None:
            _conversation_cwd[conversation_id] = new_cwd

        output = _truncate(output)

        exit_code = proc.returncode or 0
        return json.dumps({"exit_code": exit_code, "output": output})

    return AgentTool(
        name="terminal",
        description=(
            "Run a shell command in the workspace. "
            "The working directory persists across calls within the same conversation. "
            "Output is truncated to 50K characters with head/tail preservation."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
            },
            "required": ["command"],
        },
        execute=execute,
        display=make_tool_display(
            icon="💻",
            label="Terminal",
            present=lambda args: f"💻 $ {(args.get('command') or '')[:60]}",
            compact=lambda args: f"$ {(args.get('command') or '')[:40]}",
        ),
    )


def _extract_cwd(output: str) -> tuple[str, Path | None]:
    """Split sentinel-delimited output into (user_output, new_cwd)."""
    marker = f"\n{_CWD_SENTINEL}\n"
    idx = output.rfind(marker)
    if idx == -1:
        return output, None
    user_output = output[:idx]
    after = output[idx + len(marker) :]
    cwd_line = after.strip().splitlines()[0] if after.strip() else ""
    new_cwd = Path(cwd_line) if cwd_line else None
    return user_output, new_cwd


def _truncate(output: str) -> str:
    """Apply head/tail truncation if output exceeds the cap."""
    if len(output) <= _MAX_OUTPUT_CHARS:
        return output
    head_chars = int(_MAX_OUTPUT_CHARS * _HEAD_RATIO)
    tail_chars = _MAX_OUTPUT_CHARS - head_chars
    elided = len(output) - head_chars - tail_chars
    notice = f"\n\n[...{elided} characters truncated...]\n\n"
    return output[:head_chars] + notice + output[-tail_chars:]
