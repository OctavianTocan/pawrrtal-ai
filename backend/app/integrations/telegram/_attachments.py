"""Telegram inbound-attachment processing.

Closes #304 (voice transcription) and #305 (image + file ingestion).
Each attachment type maps to a single normalization step that runs
inside :func:`collect_attachments`:

* **photo** → base64 image entry, forwarded multimodally to providers
  that support it via :class:`ChatTurnInput.images`.
* **voice / audio** → transcribed via the configured backend (Mistral,
  OpenAI, local whisper.cpp). Failed or unconfigured transcription
  falls back to a bounded ``[User sent a voice message ...]``
  annotation so the agent at least knows what happened.
* **document** → converted to bounded Markdown via markitdown when the
  payload is under :data:`_MAX_FILE_BYTES`. Oversized or unsupported
  documents fall back to a metadata-only annotation.

Contract
~~~~~~~~

:func:`collect_attachments` walks an aiogram :class:`Message`, downloads
each supported attachment to memory, and returns:

* ``images`` — base64-encoded image inputs in the shape the chat router
  forwards through ``ChatTurnInput.images``. Currently the largest
  Telegram ``PhotoSize`` is selected per message.
* ``text_annotations`` — short ``"User sent X."`` lines added to the
  user message so the model has voice transcripts + document
  excerpts inline.
* ``unsupported`` — list of MIME-type strings we skipped entirely
  (e.g. animations, stickers). Logged but not surfaced to the model.

The processor never raises — Telegram delivery is best-effort, and
losing one attachment is preferable to losing the whole turn.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import Message

logger = logging.getLogger(__name__)

# Telegram caps photos at 10 MB and documents at 50 MB. We pull the
# entire file into memory to base64-encode, so cap our own download
# below Telegram's cap to keep memory predictable.
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_FILE_BYTES = 20 * 1024 * 1024

# Voice notes longer than this are still transcribed but logged
# loudly; STT backends can take many seconds per minute of audio.
_VOICE_LONG_DURATION_SECONDS = 120

# Maximum number of characters of extracted document Markdown we
# inline into the agent prompt. Beyond this the annotation is
# truncated with a clear marker — the agent can ask for a re-send if
# the truncated tail mattered.
_MAX_DOC_INLINE_CHARS = 8_000


@dataclass(frozen=True)
class TelegramAttachments:
    """Decoded payload of attachments extracted from one Telegram message."""

    #: Image inputs in the chat-router wire shape (``{data, media_type}``).
    images: list[dict[str, str]] = field(default_factory=list)
    #: Short ``"User sent X."`` lines appended to the user message so the
    #: agent knows about attachments we couldn't fully extract.
    text_annotations: list[str] = field(default_factory=list)
    #: MIME-type strings of attachments we deliberately ignored.
    unsupported: list[str] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        """Whether the message carried at least one processed attachment."""
        return bool(self.images) or bool(self.text_annotations) or bool(self.unsupported)


async def collect_attachments(message: Message, bot: Bot) -> TelegramAttachments:
    """Extract images + annotations from a Telegram :class:`Message`.

    Behavior per attachment type:

    * **photo** (``message.photo``): largest ``PhotoSize`` is downloaded,
      base64-encoded, and added to ``images``. Telegram photos are
      always JPEG; we hard-code ``image/jpeg``.
    * **voice / audio** (``message.voice`` / ``message.audio``): the
      audio is downloaded and transcribed through the configured STT
      backend; the transcript is added as a
      ``[User sent a voice message. Transcription: ...]`` annotation.
      When STT is unconfigured or fails, a metadata-only annotation
      is added instead.
    * **document** (``message.document``): converted to Markdown via
      markitdown when under the size cap, then inlined as a bounded
      excerpt. Oversized or unsupported documents fall back to a
      metadata annotation.
    * **video / animation / sticker / contact / location / poll**: skipped.

    All failures (download errors, unexpected payload shapes) are
    logged and swallowed so a single bad attachment never breaks the
    rest of the turn.
    """
    result_images: list[dict[str, str]] = []
    result_annotations: list[str] = []
    result_unsupported: list[str] = []

    if message.photo:
        await _add_largest_photo(message, bot, result_images, result_annotations)

    if message.voice is not None:
        await _add_voice_transcription(message, bot, result_annotations)

    if message.audio is not None:
        await _add_audio_transcription(message, bot, result_annotations)

    if message.document is not None:
        await _add_document_extraction(message, bot, result_annotations)

    if message.video is not None or message.animation is not None:
        result_unsupported.append("video")

    if message.sticker is not None:
        result_unsupported.append("sticker")

    return TelegramAttachments(
        images=result_images,
        text_annotations=result_annotations,
        unsupported=result_unsupported,
    )


async def _add_largest_photo(
    message: Message,
    bot: Bot,
    images: list[dict[str, str]],
    annotations: list[str],
) -> None:
    """Download the largest ``PhotoSize`` and append a base64 image entry.

    Telegram offers multiple resolutions per photo; the last entry is
    always the highest resolution. We cap the download at
    :data:`_MAX_IMAGE_BYTES` so a misbehaving client can't blow our
    memory budget.
    """
    if not message.photo:
        return
    largest = message.photo[-1]
    file_size = getattr(largest, "file_size", None) or 0
    if file_size and file_size > _MAX_IMAGE_BYTES:
        annotations.append(
            f"[User sent an image but it was too large to forward "
            f"({file_size} bytes > {_MAX_IMAGE_BYTES} cap).]"
        )
        return
    raw_bytes = await _download_file(bot, largest.file_id, label="photo")
    if raw_bytes is None:
        annotations.append("[User sent an image but we couldn't download it for analysis.]")
        return
    images.append(
        {
            "data": base64.b64encode(raw_bytes).decode("ascii"),
            "media_type": "image/jpeg",
        }
    )


async def _add_voice_transcription(
    message: Message,
    bot: Bot,
    annotations: list[str],
) -> None:
    """Download + transcribe a Telegram voice message."""
    voice = message.voice
    duration = getattr(voice, "duration", None) or 0
    file_id = getattr(voice, "file_id", None)
    if not file_id:
        annotations.append(f"[User sent a voice message ({duration}s) but it had no file id.]")
        return
    file_size = getattr(voice, "file_size", None) or 0
    if file_size and file_size > _MAX_FILE_BYTES:
        annotations.append(
            f"[User sent a voice message ({duration}s) but it was too large to transcribe "
            f"({file_size} bytes > {_MAX_FILE_BYTES} cap).]"
        )
        return
    if duration > _VOICE_LONG_DURATION_SECONDS:
        logger.info("TELEGRAM_VOICE_LONG duration=%d", duration)

    raw_bytes = await _download_file(bot, file_id, label="voice")
    if raw_bytes is None:
        annotations.append(
            f"[User sent a voice message ({duration}s) but we couldn't download it.]"
        )
        return

    transcript = await _transcribe_audio(raw_bytes)
    if transcript is None:
        annotations.append(
            f"[User sent a voice message ({duration}s). "
            "Transcription is not available on this surface yet — ask the "
            "user to retype the relevant bits if it matters.]"
        )
        return
    annotations.append(f"[User sent a voice message ({duration}s). Transcription: {transcript}]")


async def _add_audio_transcription(
    message: Message,
    bot: Bot,
    annotations: list[str],
) -> None:
    """Download + transcribe a Telegram audio file (treated like voice)."""
    audio = message.audio
    title = getattr(audio, "title", None) or "audio clip"
    duration = getattr(audio, "duration", None) or 0
    file_id = getattr(audio, "file_id", None)
    file_size = getattr(audio, "file_size", None) or 0
    if not file_id or (file_size and file_size > _MAX_FILE_BYTES):
        annotations.append(f"[User sent an audio file: {title} ({duration}s).]")
        return

    raw_bytes = await _download_file(bot, file_id, label="audio")
    if raw_bytes is None:
        annotations.append(f"[User sent an audio file: {title} ({duration}s).]")
        return

    transcript = await _transcribe_audio(raw_bytes)
    if transcript is None:
        annotations.append(f"[User sent an audio file: {title} ({duration}s).]")
        return
    annotations.append(
        f"[User sent an audio file: {title} ({duration}s). Transcription: {transcript}]"
    )


async def _add_document_extraction(
    message: Message,
    bot: Bot,
    annotations: list[str],
) -> None:
    """Download + markitdown-extract a Telegram document attachment."""
    document = message.document
    file_name = getattr(document, "file_name", None) or "(unnamed)"
    mime = getattr(document, "mime_type", None) or "application/octet-stream"
    size = getattr(document, "file_size", None) or 0
    file_id = getattr(document, "file_id", None)

    if not file_id:
        annotations.append(f"[User sent a document: {file_name} ({mime}, {size} bytes).]")
        return
    if size and size > _MAX_FILE_BYTES:
        annotations.append(
            f"[User sent a document: {file_name} ({mime}, {size} bytes). "
            f"Too large to extract inline (> {_MAX_FILE_BYTES} cap).]"
        )
        return

    raw_bytes = await _download_file(bot, file_id, label="document")
    if raw_bytes is None:
        annotations.append(
            f"[User sent a document: {file_name} ({mime}, {size} bytes). "
            "Inline extraction failed at the download step.]"
        )
        return

    markdown = await _extract_markdown_from_bytes(raw_bytes, file_name=file_name)
    if markdown is None:
        annotations.append(
            f"[User sent a document: {file_name} ({mime}, {size} bytes). "
            "Inline extraction failed — ask the user to paste the relevant text.]"
        )
        return

    excerpt, truncated = _bounded_excerpt(markdown, _MAX_DOC_INLINE_CHARS)
    suffix = " (truncated)" if truncated else ""
    annotations.append(
        f"[User sent a document: {file_name} ({mime}, {size} bytes). "
        f"Extracted Markdown{suffix}:\n{excerpt}]"
    )


async def _download_file(bot: Bot, file_id: str, *, label: str) -> bytes | None:
    """Best-effort download of a Telegram file, returning ``None`` on failure."""
    try:
        file = await bot.get_file(file_id)
        file_path = getattr(file, "file_path", None)
        if not file_path:
            logger.warning("TELEGRAM_%s_NO_FILE_PATH file_id=%s", label.upper(), file_id)
            return None
        downloaded = await bot.download_file(file_path)
        raw_bytes = downloaded.read() if downloaded is not None else b""
        if not raw_bytes:
            logger.warning("TELEGRAM_%s_EMPTY_DOWNLOAD file_id=%s", label.upper(), file_id)
            return None
        return raw_bytes
    except Exception:
        logger.exception(
            "TELEGRAM_%s_DOWNLOAD_FAILED file_id=%s",
            label.upper(),
            file_id,
        )
        return None


async def _transcribe_audio(audio_bytes: bytes) -> str | None:
    """Transcribe via the configured backend, returning ``None`` on failure.

    Resolves :func:`app.integrations.voice.resolve_transcriber` once
    per call.  When the resolver returns ``None`` (operator hasn't
    configured a voice backend or the corresponding API key is unset)
    the bot falls back to the metadata-only annotation.  Any backend
    failure is logged and swallowed; voice ingestion must never break
    a turn.

    All four backends — xAI, Mistral, OpenAI, local whisper.cpp — are
    valid here; the previous behaviour where ``voice_provider == "xai"``
    silently skipped was the reported Telegram-voice bug.
    """
    from app.integrations.voice import (  # noqa: PLC0415 — optional dep
        TranscriptionError,
        resolve_transcriber,
    )

    transcriber = resolve_transcriber()
    if transcriber is None:
        return None
    try:
        text = await transcriber.transcribe(audio_bytes)
    except TranscriptionError as exc:
        logger.warning("TELEGRAM_VOICE_TRANSCRIBE_FAIL error=%s", exc)
        return None
    except Exception:
        logger.exception("TELEGRAM_VOICE_TRANSCRIBE_UNEXPECTED")
        return None
    return text.strip() or None


async def _extract_markdown_from_bytes(raw_bytes: bytes, *, file_name: str) -> str | None:
    """Run markitdown on ``raw_bytes`` written to a tempfile.

    markitdown drives format selection from the file extension on the
    path it's given, so we preserve the original ``file_name`` suffix
    inside a private tempdir. The tempdir is cleaned up unconditionally
    so a conversion crash doesn't leak disk.

    The synchronous markitdown call is offloaded to a thread via
    ``asyncio.to_thread`` so the bot's event loop keeps servicing
    other updates while the conversion runs.
    """
    suffix = Path(file_name).suffix or ".bin"
    tmp_dir = tempfile.mkdtemp(prefix="pawrrtal-tg-doc-")
    try:
        target = Path(tmp_dir) / f"input{suffix}"
        target.write_bytes(raw_bytes)
        return await asyncio.to_thread(_run_markitdown_sync, target)
    except Exception:
        logger.exception("TELEGRAM_DOC_EXTRACT_FAILED file_name=%s", file_name)
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_markitdown_sync(path: Path) -> str | None:
    """Invoke markitdown synchronously — meant for ``asyncio.to_thread``."""
    try:
        from markitdown import MarkItDown  # noqa: PLC0415 — heavy optional dep
    except ImportError:
        logger.warning("MARKITDOWN_MISSING — cannot extract Telegram documents")
        return None
    result = MarkItDown(enable_plugins=False).convert(str(path))
    text = (getattr(result, "text_content", "") or "").strip()
    return text or None


def _bounded_excerpt(text: str, max_chars: int) -> tuple[str, bool]:
    """Return ``(excerpt, truncated)`` capped at ``max_chars``."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + "…", True
