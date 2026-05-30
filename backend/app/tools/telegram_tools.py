"""Telegram-specific capability tools surfaced to the agent (PR 13).

CCT exposes ``send_image_to_user`` etc. as MCP tools so Claude can
choose to call them.  We already have a generic ``send_message``
tool that's MIME-aware; this module adds three thin convenience
wrappers (``send_image_to_user``, ``send_voice_to_user``,
``send_document_to_user``) so a workspace authored against CCT's
MCP names "just works" against our agent.

Each wrapper does the same path validation CCT does:
* file path must be absolute
* extension must match the tool's allowlist
* file must exist

…and then delegates to the same ``SendFn`` callback the
``send_message`` tool uses.  No new transport, no new MCP server —
the existing ``_claude_tool_bridge`` mounts these alongside the rest.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.types import AgentTool
from app.tools.display import make_tool_display, summarize_path
from app.tools.send_message import SendFn

_IMAGE_EXTS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"})
_VOICE_EXTS: frozenset[str] = frozenset({".ogg", ".opus", ".mp3", ".m4a", ".wav"})
_DOCUMENT_EXTS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".txt",
        ".md",
        ".csv",
        ".json",
        ".html",
        ".xml",
        ".yaml",
        ".yml",
        ".doc",
        ".docx",
        ".zip",
    }
)


def _validate_path(file_path: str, allowed_exts: frozenset[str]) -> Path | str:
    """Return a resolved Path or an error string the agent can read."""
    path = Path(file_path)
    if not path.is_absolute():
        return f"Error: file_path must be absolute, got '{file_path}'"
    if path.suffix.lower() not in allowed_exts:
        return (
            f"Error: extension '{path.suffix}' not in allowlist; "
            f"supported: {', '.join(sorted(allowed_exts))}"
        )
    if not path.is_file():
        return f"Error: file not found at '{file_path}'"
    return path


def _media_for_extension(suffix: str) -> str:
    """Best-effort MIME guess for the channel's MIME-aware delivery."""
    table = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".json": "application/json",
    }
    return table.get(suffix.lower(), "application/octet-stream")


def _build_specialized_send_tool(
    *,
    name: str,
    description: str,
    allowed_exts: frozenset[str],
    send_fn: SendFn,
    icon: str,
    label: str,
) -> AgentTool:
    """Build one specialized ``send_*_to_user`` tool."""

    async def execute(
        _tool_call_id: str,
        *,
        file_path: str,
        caption: str | None = None,
    ) -> str:
        resolved = _validate_path(file_path, allowed_exts)
        if isinstance(resolved, str):
            return resolved
        await send_fn(caption, resolved, _media_for_extension(resolved.suffix))
        return f"Sent {resolved.name} to the user."

    return AgentTool(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file on disk.",
                },
                "caption": {
                    "type": "string",
                    "description": "Optional caption shown alongside the file.",
                },
            },
            "required": ["file_path"],
        },
        execute=execute,
        display=make_tool_display(
            icon=icon,
            label=label,
            present=lambda args: f"{icon} Sending {summarize_path(args.get('file_path'))}",
            compact=lambda args: f"{label} -> {summarize_path(args.get('file_path'))}",
        ),
    )


def make_telegram_capability_tools(send_fn: SendFn) -> list[AgentTool]:
    """Return the three CCT-shaped Telegram capability tools.

    Bound to the per-request ``SendFn`` so they share the same
    delivery path as the existing ``send_message`` tool.
    """
    return [
        _build_specialized_send_tool(
            name="send_image_to_user",
            description=(
                "Send an image file (PNG, JPEG, GIF, WebP, …) to the "
                "user.  The file must already exist on disk; use "
                "image_gen first if you need to create one."
            ),
            allowed_exts=_IMAGE_EXTS,
            send_fn=send_fn,
            icon="🖼",
            label="Send image",
        ),
        _build_specialized_send_tool(
            name="send_voice_to_user",
            description=(
                "Send a voice / audio file (OGG, MP3, M4A, WAV, Opus) "
                "to the user.  OGG / Opus render as voice notes; other "
                "formats render as audio attachments."
            ),
            allowed_exts=_VOICE_EXTS,
            send_fn=send_fn,
            icon="🎙",
            label="Send voice",
        ),
        _build_specialized_send_tool(
            name="send_document_to_user",
            description=(
                "Send a document (PDF, MD, CSV, JSON, ZIP, …) to the "
                "user as a downloadable attachment."
            ),
            allowed_exts=_DOCUMENT_EXTS,
            send_fn=send_fn,
            icon="📎",
            label="Send document",
        ),
    ]
