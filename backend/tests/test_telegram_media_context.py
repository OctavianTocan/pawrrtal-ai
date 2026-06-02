"""Tests for Telegram media preprocessing before the Paw agent turn."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from app.channels.telegram._attachments import TelegramVoiceNote
from app.channels.telegram.media_context import prepare_telegram_media_context
from app.infrastructure.config import Settings
from app.providers.base import StreamEvent
from app.providers.model_id import Host, parse_model_id

pytestmark = pytest.mark.anyio


class _FakeImageProvider:
    """Provider stub that records image inputs and returns one text delta."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append(
            {
                "question": question,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "kwargs": kwargs,
            }
        )
        yield {"type": "delta", "content": "The image shows a red cube on a desk."}


async def test_prepare_media_context_interprets_images_with_sub_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Image bytes become a text annotation and are not sent to the main model."""
    provider = _FakeImageProvider()
    monkeypatch.setattr(
        "app.channels.telegram.media_context.resolve_llm",
        lambda model_id, *, workspace_root: provider,
    )
    monkeypatch.setattr(
        "app.channels.telegram.media_context.settings.telegram_image_interpreter_model_id",
        "google-ai:google/gemini-3.5-flash",
    )

    annotations = await prepare_telegram_media_context(
        images=[{"data": "YWJj", "media_type": "image/jpeg"}],
        voice_notes=[],
        text_annotations=[],
        workspace_root=tmp_path,
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user_prompt="What is in this picture?",
    )

    assert len(provider.calls) == 1
    assert provider.calls[0]["kwargs"]["images"] == [{"data": "YWJj", "media_type": "image/jpeg"}]
    assert provider.calls[0]["kwargs"]["tools"] is None
    assert "What is in this picture?" in provider.calls[0]["question"]
    assert "Image understanding sub-agent" in annotations[0]
    assert "red cube" in annotations[0]


async def test_prepare_media_context_transcribes_voice_note_with_xai_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Voice notes become explicit transcript annotations before the agent turn."""
    captured: dict[str, Any] = {}

    async def fake_transcribe(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "Please remind me to test the Telegram voice path."

    monkeypatch.setattr("app.channels.telegram.media_context.transcribe_xai_stt", fake_transcribe)
    note = TelegramVoiceNote(
        raw_bytes=b"OggS voice",
        duration_seconds=3,
        mime_type="audio/ogg",
        file_name="voice.ogg",
    )

    annotations = await prepare_telegram_media_context(
        images=[],
        voice_notes=[note],
        text_annotations=[],
        workspace_root=tmp_path,
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user_prompt="",
    )

    assert captured["workspace_root"] == tmp_path
    assert captured["raw_bytes"] == b"OggS voice"
    assert captured["mime_type"] == "audio/ogg"
    assert "Transcription from user voice note" in annotations[0]
    assert "Please remind me" in annotations[0]


def test_default_telegram_image_interpreter_model_id_is_parseable() -> None:
    """The default media helper model must stay a valid Paw model ID."""
    default_model_id = Settings.model_fields["telegram_image_interpreter_model_id"].default

    parsed = parse_model_id(str(default_model_id))

    assert parsed.host == Host.google_ai
