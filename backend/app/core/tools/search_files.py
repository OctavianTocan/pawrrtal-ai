"""Workspace-scoped file search via ripgrep.

Wraps ``rg`` (ripgrep) for fast, gitignore-aware content search within
the workspace root.  Ripgrep is a deployment dependency — the tool
returns a clear error when ``rg`` is not on ``$PATH``.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.tools.display import make_tool_display

log = logging.getLogger(__name__)

_MAX_OUTPUT_BYTES = 50_000
_FIRST_40_CHARS = 40


def make_search_files_tool(*, workspace_root: Path) -> AgentTool:
    """Return the ``search_files`` AgentTool scoped to *workspace_root*."""
    root = Path(workspace_root).resolve()

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        sub_path = kwargs.get("path", "")
        include = kwargs.get("include", "")

        if not query:
            return "Error: 'query' is required."

        search_dir = root
        if sub_path:
            candidate = (root / sub_path).resolve()
            if not candidate.is_relative_to(root):
                return "Error: path is outside the workspace root."
            search_dir = candidate

        if not shutil.which("rg"):
            return "Error: ripgrep (rg) is not installed."

        cmd = ["rg", "--line-number", "--no-heading", "--color=never", query]
        if include:
            cmd.extend(["--glob", include])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(search_dir),
        )
        stdout, _stderr = await proc.communicate()

        output = stdout.decode("utf-8", errors="replace")
        if not output.strip():
            return "No matches found."

        if len(output) > _MAX_OUTPUT_BYTES:
            output = output[:_MAX_OUTPUT_BYTES] + "\n[...truncated]"

        return output

    return AgentTool(
        name="search_files",
        description=(
            "Search workspace files for a text pattern using ripgrep. "
            "Returns matching lines with file paths and line numbers. "
            "Respects .gitignore by default."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search pattern (string or regex).",
                },
                "path": {
                    "type": "string",
                    "description": "Optional subdirectory to scope the search to.",
                },
                "include": {
                    "type": "string",
                    "description": "Optional glob pattern to filter files (e.g. '*.py').",
                },
            },
            "required": ["query"],
        },
        execute=execute,
        display=make_tool_display(
            icon="🔍",
            label="Search files",
            present=lambda args: (
                f"🔍 Searching for: {(args.get('query') or '')[:_FIRST_40_CHARS]}"
            ),
            compact=lambda args: f"search({args.get('query', '')[:20]})",
        ),
    )
