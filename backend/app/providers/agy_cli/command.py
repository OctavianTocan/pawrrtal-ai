"""Command construction helpers for the Antigravity ``agy`` CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

AGY_BINARY_NAME = "agy"
DEFAULT_PRINT_TIMEOUT = "10m"


def is_agy_cli_available() -> bool:
    """Return whether the ``agy`` binary is resolvable on ``PATH``."""
    return shutil.which(AGY_BINARY_NAME) is not None


def build_agy_command(
    *,
    workspace_roots: list[Path],
    log_file: Path,
    prompt: str,
    timeout: str = DEFAULT_PRINT_TIMEOUT,
    conversation_id: str | None = None,
) -> list[str]:
    """Build the argv for one non-interactive ``agy --print`` turn."""
    command = [AGY_BINARY_NAME]
    for root in workspace_roots:
        command.extend(["--add-dir", str(root)])
    if conversation_id:
        command.extend(["--conversation", conversation_id])
    command.extend(
        [
            "--log-file",
            str(log_file),
            "--print-timeout",
            timeout,
            "--print",
            prompt,
        ]
    )
    return command
