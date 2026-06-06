"""Inbound attachment handling for the Google Chat channel.

Mirrors the Telegram attachment pipeline (``telegram/_attachments.py``) for
Google Chat's add-on event shape:

* **image** (``image/*``) → base64 entry for the pre-turn vision sub-agent.
* **document** (other types) → bounded Markdown via markitdown, inlined as a
  ``[User sent a document: …]`` annotation.
* **audio** (``audio/*``) → metadata-only annotation (transcription is
  intentionally disabled post-restructure: voice reaches the agent as a note).
* **Drive file / oversized / undownloadable** → metadata-only annotation.

Attachments arrive on ``message.attachment[]``. ``UPLOADED_CONTENT`` bytes
are fetched from the Chat media endpoint; ``DRIVE_FILE`` attachments can't be
read there, so they're annotated rather than downloaded.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import download_attachment
from .messages import attachments_of

logger = logging.getLogger(__name__)

# In-memory download caps. Chat permits up to 200 MB uploads, but we only
# inline small payloads; larger ones degrade to a metadata annotation.
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_FILE_BYTES = 20 * 1024 * 1024
_MAX_DOC_INLINE_CHARS = 8000

_DRIVE_FILE_SOURCE = "DRIVE_FILE"


@dataclass
class GoogleChatAttachments:
    """Collected attachment inputs for one inbound message."""

    #: Base64 image entries in the ``ChatTurnInput.images`` shape.
    images: list[dict[str, str]] = field(default_factory=list)
    #: ``[User sent …]`` lines appended to the user's question text.
    annotations: list[str] = field(default_factory=list)


async def collect_attachments(event: dict[str, Any]) -> GoogleChatAttachments:
    """Process every attachment on the inbound message (best-effort)."""
    result = GoogleChatAttachments()
    for attachment in attachments_of(event):
        await _process_attachment(attachment, result)
    return result


async def _process_attachment(attachment: dict[str, Any], result: GoogleChatAttachments) -> None:
    name = str(attachment.get("contentName") or "(unnamed)")
    content_type = str(attachment.get("contentType") or "application/octet-stream")
    if str(attachment.get("source") or "") == _DRIVE_FILE_SOURCE:
        result.annotations.append(
            f"[User shared a Drive file: {name} ({content_type}); not readable via Chat.]"
        )
        return
    resource = (attachment.get("attachmentDataRef") or {}).get("resourceName")
    if not resource:
        result.annotations.append(
            f"[User sent {name} ({content_type}) but it had no downloadable reference.]"
        )
        return
    if content_type.startswith("image/"):
        await _add_image(str(resource), content_type, name, result)
    elif content_type.startswith("audio/"):
        result.annotations.append(f"[User sent a voice/audio message: {name} ({content_type}).]")
    else:
        await _add_document(str(resource), name, content_type, result)


async def _add_image(
    resource: str, content_type: str, name: str, result: GoogleChatAttachments
) -> None:
    raw = await download_attachment(resource_name=resource, max_bytes=_MAX_IMAGE_BYTES)
    if raw is None:
        result.annotations.append(
            f"[User sent an image {name} but it couldn't be fetched for analysis.]"
        )
        return
    result.images.append(
        {"data": base64.b64encode(raw).decode("ascii"), "media_type": content_type}
    )


async def _add_document(
    resource: str, name: str, content_type: str, result: GoogleChatAttachments
) -> None:
    raw = await download_attachment(resource_name=resource, max_bytes=_MAX_FILE_BYTES)
    if raw is None:
        result.annotations.append(
            f"[User sent a document: {name} ({content_type}); couldn't fetch it for extraction.]"
        )
        return
    markdown = await _extract_markdown(raw, file_name=name)
    if markdown is None:
        result.annotations.append(
            f"[User sent a document: {name} ({content_type}); inline extraction failed — "
            "ask them to paste the relevant text.]"
        )
        return
    excerpt, truncated = _bounded_excerpt(markdown, _MAX_DOC_INLINE_CHARS)
    suffix = " (truncated)" if truncated else ""
    result.annotations.append(
        f"[User sent a document: {name} ({content_type}). Extracted Markdown{suffix}:\n{excerpt}]"
    )


async def _extract_markdown(raw_bytes: bytes, *, file_name: str) -> str | None:
    """Convert ``raw_bytes`` to Markdown via markitdown, off the event loop.

    markitdown selects the converter from the file extension, so the
    original suffix is preserved inside a private tempdir that is always
    cleaned up. The synchronous conversion is offloaded with
    ``asyncio.to_thread`` so the pull loop keeps servicing events.
    """
    suffix = Path(file_name).suffix or ".bin"
    tmp_dir = tempfile.mkdtemp(prefix="pawrrtal-gchat-doc-")
    try:
        target = Path(tmp_dir) / f"input{suffix}"
        target.write_bytes(raw_bytes)
        return await asyncio.to_thread(_run_markitdown_sync, target)
    except Exception:
        logger.exception("GOOGLE_CHAT_DOC_EXTRACT_FAILED file_name=%s", file_name)
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_markitdown_sync(path: Path) -> str | None:
    """Invoke markitdown synchronously — meant for ``asyncio.to_thread``."""
    try:
        from markitdown import MarkItDown  # noqa: PLC0415 — heavy optional dep
    except ImportError:
        logger.warning("MARKITDOWN_MISSING — cannot extract Google Chat documents")
        return None
    result = MarkItDown(enable_plugins=False).convert(str(path))
    text = (getattr(result, "text_content", "") or "").strip()
    return text or None


def _bounded_excerpt(text: str, max_chars: int) -> tuple[str, bool]:
    """Return ``(excerpt, truncated)`` capped at ``max_chars``."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + "…", True
