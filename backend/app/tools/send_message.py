"""send_message AgentTool — channel-aware media delivery.

This tool is the LLM's explicit delivery primitive.  When the agent generates
an artifact (image, audio, document) it saves it to the workspace first, then
calls ``send_message`` to hand it off.  The tool is intentionally thin:

- It resolves and validates the workspace-relative path.
- It detects the MIME type.
- It calls the injected ``SendFn`` callback — which is channel-specific and
  assembled at request time by the channel's own factory.

The LLM never knows which channel it's in.  The channel decides *how* to
deliver (sendPhoto vs sendVoice vs sendDocument) based on MIME alone.

Architecture contract
---------------------
``make_send_message_tool`` is a factory — exactly like ``make_workspace_tools``
in ``workspace_files.py``.  It binds a workspace root and a ``SendFn`` at
construction time so the tool body stays pure and testable without mocking
HTTP or Telegram internals.

``SendFn`` signature::

    async def send(
        text: str | None,
        file_path: Path | None,
        mime: str | None,
    ) -> None: ...

The channel implementation is responsible for all error handling inside
``SendFn``; the tool catches unexpected exceptions and returns an error string
so the agent can react rather than crash.
"""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.agents.types import AgentTool
from app.tools.display import make_tool_display, summarize_path
from app.tools.errors import ToolError, ToolErrorCode

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SendFn protocol (structural — no runtime ABC overhead)
# ---------------------------------------------------------------------------

SendFn = Callable[
    [str | None, Path | None, str | None],
    Awaitable[None],
]
"""Async callable injected by the channel layer.

Args:
    text:      Optional message text to accompany the media (or standalone).
    file_path: Absolute, validated path to the file to send.  None = text only.
    mime:      MIME type string e.g. ``"image/png"``.  None when no file.
"""


# ---------------------------------------------------------------------------
# Path resolution (same invariant as workspace_files._resolve_safe)
# ---------------------------------------------------------------------------


def _resolve_attachment(root: Path, rel_path: str) -> Path:
    """Resolve *rel_path* inside *root*, rejecting traversal attempts.

    Raises :class:`ToolError` on failure.
    """
    try:
        target = (root / rel_path.lstrip("/")).resolve()
    except (OSError, ValueError) as exc:
        raise ToolError(
            ToolErrorCode.INVALID_PATH,
            f"Cannot resolve attachment path '{rel_path}': {exc}",
        ) from exc

    if not str(target).startswith(str(root.resolve())):
        raise ToolError(
            ToolErrorCode.OUT_OF_ROOT,
            f"Attachment path '{rel_path}' resolves outside the workspace.",
        )
    if not target.exists():
        raise ToolError(
            ToolErrorCode.NOT_FOUND,
            f"Attachment '{rel_path}' does not exist in the workspace.",
        )
    if not target.is_file():
        raise ToolError(
            ToolErrorCode.WRONG_KIND,
            f"Attachment '{rel_path}' is a directory, not a file.",
        )
    return target


def _detect_mime(path: Path) -> str:
    """Best-effort MIME detection from file extension.

    Falls back to ``application/octet-stream`` when the extension is unknown,
    which channels should treat as "send as a document/download".
    """
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------


def make_send_message_tool(
    *,
    workspace_root: Path,
    send_fn: SendFn,
) -> AgentTool:
    """Return a ``send_message`` :class:`AgentTool` scoped to *workspace_root*.

    The returned tool is ready to pass into ``AgentContext.tools``.  It is
    safe to call from multiple concurrent turns — all mutable state lives in
    the ``SendFn`` closure, which the channel is responsible for making safe.

    Args:
        workspace_root: Absolute path to the user's workspace directory.
            Attachment paths the agent provides are validated against this root.
        send_fn: Channel-specific async delivery callback.  Called with the
            resolved file path and detected MIME type.

    Returns:
        A fully configured :class:`AgentTool` named ``"send_message"``.
    """
    root = Path(workspace_root).resolve()

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        text: str | None = kwargs.get("text") or None
        attachment: str | None = kwargs.get("attachment") or None

        if not text and not attachment:
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "send_message requires at least one of: 'text', 'attachment'.",
            ).render()

        file_path: Path | None = None
        mime: str | None = None

        if attachment:
            try:
                file_path = _resolve_attachment(root, attachment)
            except ToolError as err:
                return err.render()
            mime = _detect_mime(file_path)

        try:
            await send_fn(text, file_path, mime)
        except Exception as exc:
            log.warning("SEND_MESSAGE_FAILED attachment=%s error=%s", attachment, exc)
            return f'{{"sent": false, "error": "{exc}"}}'

        result: dict[str, Any] = {"sent": True}
        if file_path is not None:
            result["path"] = str(file_path.relative_to(root))
            result["mime"] = mime
        return str(result).replace("'", '"')

    return AgentTool(
        name="send_message",
        description=(
            "Send a message to the user, optionally with a file attachment.\n\n"
            "Use this after generating any artifact the user asked to see — "
            "images, audio clips, documents, code archives, etc.\n\n"
            "``attachment`` must be a workspace-relative path to a file you "
            "previously wrote with ``write_file``.  The channel will choose the "
            "appropriate delivery method based on file type (photo, voice, "
            "document, etc.) — you do not need to specify it.\n\n"
            "At least one of ``text`` or ``attachment`` must be provided."
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "Optional message text to accompany the file, "
                        "or a standalone text message when no attachment is provided."
                    ),
                },
                "attachment": {
                    "type": "string",
                    "description": (
                        "Workspace-relative path to the file to send, "
                        "e.g. 'artifacts/cat.png' or 'generated/report.pdf'. "
                        "Omit to send text only."
                    ),
                },
            },
            "required": [],
        },
        execute=execute,
        display=make_tool_display(
            icon="💬",
            label="Send Message",
            present=_send_message_present,
            compact=_send_message_compact,
        ),
    )


def _send_message_present(args: dict[str, Any]) -> str:
    attachment = args.get("attachment")
    if attachment:
        return f"💬 Sending {summarize_path(attachment)}"
    return "💬 Sending message"


def _send_message_compact(args: dict[str, Any]) -> str:
    attachment = args.get("attachment")
    if attachment:
        return f"Send message -> {summarize_path(attachment)}"
    return "Send message"
