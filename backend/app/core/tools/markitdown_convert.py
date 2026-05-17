"""Convert workspace files to Markdown via the markitdown library.

Provides ``make_markitdown_tool`` which returns an ``AgentTool`` that lets
the agent convert documents (PDF, DOCX, XLSX, PPTX, HTML, …) to Markdown
text.  The returned string can be inspected inline or saved with
``write_file``.

markitdown is a synchronous library.  All conversion calls are offloaded
to a thread via ``anyio.to_thread.run_sync`` so the event loop is not
blocked during potentially long-running conversions (e.g. large PDFs).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import anyio
from markitdown import MarkItDown

from app.core.agent_loop.types import AgentTool
from app.core.tools.display import make_tool_display, summarize_path
from app.core.tools.errors import ToolError, ToolErrorCode

log = logging.getLogger(__name__)

_EMPTY_DOCUMENT_PLACEHOLDER = "(empty document)"


def _resolve_safe(root: Path, rel_path: str) -> Path:
    """Resolve *rel_path* within *root*, rejecting path traversal.

    Args:
        root: Absolute, resolved workspace root.
        rel_path: Workspace-relative path supplied by the agent.

    Raises:
        ToolError: ``INVALID_PATH`` when the path cannot be resolved,
            ``OUT_OF_ROOT`` when it escapes the workspace.
    """
    try:
        target = (root / rel_path.lstrip("/")).resolve()
    except (OSError, ValueError) as exc:
        raise ToolError(
            ToolErrorCode.INVALID_PATH,
            f"Could not resolve path '{rel_path}': {exc}",
        ) from exc
    if not str(target).startswith(str(root)):
        raise ToolError(
            ToolErrorCode.OUT_OF_ROOT,
            f"Path '{rel_path}' resolves outside the workspace root.",
        )
    return target


def make_markitdown_tool(*, workspace_root: Path) -> AgentTool:
    """Return a ``convert_to_markdown`` AgentTool scoped to *workspace_root*.

    The tool accepts a workspace-relative file path and returns the
    Markdown representation produced by markitdown.  Supported source
    formats include PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx),
    HTML, CSV, JSON, XML, EPUB, ZIP, and plain-text files.

    Args:
        workspace_root: Absolute path to the workspace directory.

    Returns:
        An ``AgentTool`` named ``"convert_to_markdown"``.
    """
    root = Path(workspace_root).resolve()

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        raw_path: str = kwargs.get("path") or ""
        if not raw_path:
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "The 'path' argument is required.",
            ).render()

        try:
            target = _resolve_safe(root, raw_path)
        except ToolError as err:
            return err.render()

        if not target.exists():
            return ToolError(ToolErrorCode.NOT_FOUND, f"'{raw_path}' does not exist.").render()
        if not target.is_file():
            return ToolError(
                ToolErrorCode.WRONG_KIND,
                f"'{raw_path}' is a directory, not a file.",
            ).render()

        def _run() -> str:
            # Instantiate per-call to avoid any cross-thread state sharing.
            result = MarkItDown(enable_plugins=False).convert(str(target))
            return result.text_content or _EMPTY_DOCUMENT_PLACEHOLDER

        try:
            return await anyio.to_thread.run_sync(_run)
        except Exception as exc:
            log.exception("markitdown conversion failed for '%s'", raw_path)
            return ToolError(
                ToolErrorCode.IO_ERROR,
                f"Failed to convert '{raw_path}': {exc}",
            ).render()

    return AgentTool(
        name="convert_to_markdown",
        description=(
            "Convert a file in the workspace to Markdown text. "
            "Supports PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), "
            "HTML, CSV, JSON, XML, EPUB, ZIP archives, and plain-text formats. "
            "Returns the Markdown content as a string — inspect it inline "
            "or pass it to write_file to save as a .md file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative path to the file to convert, "
                        "e.g. 'documents/report.pdf' or 'uploads/slides.pptx'."
                    ),
                }
            },
            "required": ["path"],
        },
        execute=execute,
        display=make_tool_display(
            icon="📄",
            label="Convert to Markdown",
            present=lambda args: f"📄 Converting {summarize_path(args.get('path'))} to Markdown",
            compact=lambda args: f"Convert to Markdown -> {summarize_path(args.get('path'))}",
        ),
    )
