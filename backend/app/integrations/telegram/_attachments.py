"""Telegram inbound-attachment processing.

Closes the actionable parts of #304 (voice transcription handoff) and
#305 (image / file ingestion). Vision + STT integration in this module
focuses on the most common case (image attachments) and keeps voice /
document handling as bounded annotations so the agent at least knows
what the user sent — full transcription + extraction land alongside
this seam in follow-up work.

Contract
~~~~~~~~

:func:`collect_attachments` walks an aiogram :class:`Message`, downloads
each supported attachment to memory, and returns:

* ``images`` — base64-encoded image inputs in the shape the chat router
  forwards through ``ChatTurnInput.images``. Currently the largest
  Telegram ``PhotoSize`` is selected per message.
* ``text_annotations`` — short ``"User sent X."`` lines added to the
  user message so the model knows about attachments we couldn't
  fully extract on this surface yet (voice, generic documents).
* ``unsupported`` — list of MIME-type strings we skipped entirely
  (e.g. animations, stickers). Logged but not surfaced to the model.

The processor never raises — Telegram delivery is best-effort, and
losing one attachment is preferable to losing the whole turn.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
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
    * **voice / audio** (``message.voice`` / ``message.audio``): a
      ``"User sent a voice message ..."`` annotation is added so the
      agent knows what happened. Full transcription wiring lands in a
      follow-up PR for #304 — the STT proxy at ``/api/v1/stt`` isn't
      callable from this module without refactoring the route into a
      reusable service.
    * **document** (``message.document``): a ``"User sent a document
      ...filename..."`` annotation is added with the filename + MIME.
      Markitdown extraction lands in a follow-up PR for #305 — the
      extraction tool currently runs inside the agent's workspace and
      would need a sibling path to operate on raw bytes.
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
        duration = getattr(message.voice, "duration", None) or 0
        # #304: full STT wiring is its own PR — surface enough metadata
        # that the agent can reason about the voice message even
        # without a transcription.
        result_annotations.append(
            f"[User sent a voice message ({duration}s). "
            "Transcription is not available on this surface yet — ask the "
            "user to retype the relevant bits if it matters.]"
        )

    if message.audio is not None:
        title = getattr(message.audio, "title", None) or "audio clip"
        duration = getattr(message.audio, "duration", None) or 0
        result_annotations.append(f"[User sent an audio file: {title} ({duration}s).]")

    if message.document is not None:
        file_name = getattr(message.document, "file_name", None) or "(unnamed)"
        mime = getattr(message.document, "mime_type", None) or "application/octet-stream"
        size = getattr(message.document, "file_size", None) or 0
        # #305: markitdown extraction lands in a follow-up PR — surface
        # the metadata for now so the agent can ask clarifying
        # questions or request a re-send as text.
        result_annotations.append(
            f"[User sent a document: {file_name} ({mime}, {size} bytes). "
            "Inline extraction is not wired on this surface yet.]"
        )

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
    try:
        file = await bot.get_file(largest.file_id)
        file_path = getattr(file, "file_path", None)
        if not file_path:
            logger.warning("TELEGRAM_PHOTO_NO_FILE_PATH file_id=%s", largest.file_id)
            return
        downloaded = await bot.download_file(file_path)
        raw_bytes = downloaded.read() if downloaded is not None else b""
        if not raw_bytes:
            logger.warning("TELEGRAM_PHOTO_EMPTY_DOWNLOAD file_id=%s", largest.file_id)
            return
    except Exception:
        # Any aiogram-side error: log + move on.  Losing one
        # attachment must not break the rest of the turn.
        logger.exception("TELEGRAM_PHOTO_DOWNLOAD_FAILED file_id=%s", largest.file_id)
        annotations.append("[User sent an image but we couldn't download it for analysis.]")
        return
    images.append(
        {
            "data": base64.b64encode(raw_bytes).decode("ascii"),
            "media_type": "image/jpeg",
        }
    )
