"""Pre-turn Telegram media interpretation.

Telegram media is normalized before the selected Paw agent model sees the turn:

* Images are interpreted by a configured vision-capable sub-agent model.
* Voice notes are transcribed with xAI STT.

The main agent receives text annotations only. This makes media attachments work
for every selected provider, including text-only providers and Antigravity API
models that should not receive raw image bytes directly.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.channels.telegram._attachments import TelegramVoiceNote
from app.infrastructure.config import settings
from app.providers.xai.stt import XaiSttError, transcribe_xai_stt
from app.turns.media_interpreter import describe_images_for_turn

logger = logging.getLogger(__name__)

_IMAGE_FALLBACK_PROMPT = "Describe the attached Telegram image(s) for the next Pawrrtal agent."


async def prepare_telegram_media_context(
    *,
    images: list[dict[str, str]] | None,
    voice_notes: list[TelegramVoiceNote],
    text_annotations: list[str],
    workspace_root: Path | None,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    user_prompt: str,
) -> list[str]:
    """Return text annotations that should be appended to the user turn."""
    annotations = list(text_annotations)
    annotations.extend(
        await _voice_note_annotations(
            voice_notes=voice_notes,
            workspace_root=workspace_root,
        )
    )
    if images:
        annotations.append(
            await _image_annotation(
                images=images,
                workspace_root=workspace_root,
                conversation_id=conversation_id,
                user_id=user_id,
                user_prompt=user_prompt,
            )
        )
    return annotations


async def _voice_note_annotations(
    *,
    voice_notes: list[TelegramVoiceNote],
    workspace_root: Path | None,
) -> list[str]:
    """Transcribe voice notes and format stable annotations."""
    annotations: list[str] = []
    for index, note in enumerate(voice_notes, start=1):
        try:
            transcript = await transcribe_xai_stt(
                raw_bytes=note.raw_bytes,
                file_name=note.file_name,
                mime_type=note.mime_type,
                workspace_root=workspace_root,
            )
        except XaiSttError as exc:
            logger.warning("TELEGRAM_VOICE_STT_FAILED index=%d error=%s", index, exc)
            annotations.append(
                f"[User sent a voice note ({note.duration_seconds}s), but transcription failed: {exc}]"
            )
            continue
        annotations.append(
            f"[Transcription from user voice note ({note.duration_seconds}s):\n{transcript}]"
        )
    return annotations


async def _image_annotation(
    *,
    images: list[dict[str, str]],
    workspace_root: Path | None,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    user_prompt: str,
) -> str:
    """Describe images with the configured vision-capable sub-agent."""
    model_id = settings.telegram_image_interpreter_model_id
    try:
        description = await describe_images_for_turn(
            images=images,
            model_id=model_id,
            workspace_root=workspace_root,
            user_id=user_id,
            user_prompt=user_prompt,
            fallback_prompt=_IMAGE_FALLBACK_PROMPT,
        )
    except Exception as exc:
        logger.warning(
            "TELEGRAM_IMAGE_INTERPRET_FAILED conversation_id=%s model_id=%s",
            conversation_id,
            model_id,
            exc_info=True,
        )
        return f"[User attached {len(images)} image(s), but image analysis failed: {exc}]"
    return (
        f"[Image understanding sub-agent ({model_id}) described {len(images)} image(s):\n"
        f"{description}]"
    )
