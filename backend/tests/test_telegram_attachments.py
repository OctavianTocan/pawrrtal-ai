"""Tests for ``app.channels.telegram._attachments``.

Closes the actionable parts of #304 + #305: the collect_attachments
helper turns Telegram :class:`Message` payloads into image inputs +
text annotations for the chat router.
"""

from __future__ import annotations

import base64
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.channels.telegram._attachments import collect_attachments  # noqa: E402

pytestmark = pytest.mark.anyio


def _make_message(**overrides: Any) -> Message:
    """Build a minimal stub of an aiogram Message with attachment slots.

    Returns a ``Message``-typed ``SimpleNamespace`` so the test assertions
    typecheck — the production callers only read the attachment-related
    attributes that ``defaults`` covers.
    """
    defaults: dict[str, Any] = {
        "text": None,
        "caption": None,
        "photo": None,
        "voice": None,
        "audio": None,
        "document": None,
        "video": None,
        "animation": None,
        "sticker": None,
    }
    defaults.update(overrides)
    return cast(Message, SimpleNamespace(**defaults))


def _make_bot_with_photo(raw_bytes: bytes) -> AsyncMock:
    bot = AsyncMock()
    bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="photos/abc.jpg"))

    async def _download(_path: str) -> BytesIO:
        return BytesIO(raw_bytes)

    bot.download_file = _download
    return bot


async def test_text_only_message_yields_empty_attachments() -> None:
    message = _make_message(text="hi")
    bot = AsyncMock()
    attachments = await collect_attachments(message, bot)
    assert not attachments.has_any
    assert attachments.images == []


async def test_photo_message_returns_base64_image_input() -> None:
    raw = b"\xff\xd8\xff\xe0fake-jpeg"
    photo_size = SimpleNamespace(file_id="largest", file_size=len(raw))
    message = _make_message(photo=[photo_size])
    bot = _make_bot_with_photo(raw)

    attachments = await collect_attachments(message, bot)

    assert len(attachments.images) == 1
    entry = attachments.images[0]
    assert entry["media_type"] == "image/jpeg"
    assert base64.b64decode(entry["data"]) == raw


async def test_oversized_photo_is_skipped_with_annotation() -> None:
    photo_size = SimpleNamespace(file_id="too-big", file_size=99_999_999)
    message = _make_message(photo=[photo_size])
    bot = AsyncMock()
    bot.get_file = AsyncMock(side_effect=AssertionError("should not be called"))

    attachments = await collect_attachments(message, bot)

    assert attachments.images == []
    assert any("too large" in line for line in attachments.text_annotations)


async def test_voice_message_without_file_id_emits_metadata_annotation() -> None:
    message = _make_message(voice=SimpleNamespace(duration=7))
    attachments = await collect_attachments(message, AsyncMock())
    assert any(
        "voice message" in line.lower() and "7s" in line for line in attachments.text_annotations
    )


async def test_voice_message_downloads_payload_for_pre_turn_transcription() -> None:
    """Voice notes are downloaded so xAI STT can run before the agent turn."""
    raw = b"OggS\x00fake-voice"
    message = _make_message(
        voice=SimpleNamespace(
            duration=4,
            file_id="voice-id",
            file_size=len(raw),
            mime_type="audio/ogg",
        ),
    )
    bot = _make_bot_with_photo(raw)

    attachments = await collect_attachments(message, bot)
    assert len(attachments.voice_notes) == 1
    note = attachments.voice_notes[0]
    assert note.raw_bytes == raw
    assert note.duration_seconds == 4
    assert note.mime_type == "audio/ogg"
    assert attachments.text_annotations == []


async def test_document_message_without_file_id_falls_back_to_metadata() -> None:
    document = SimpleNamespace(file_name="report.pdf", mime_type="application/pdf", file_size=12345)
    message = _make_message(document=document)
    attachments = await collect_attachments(message, AsyncMock())
    annotation = next(
        (line for line in attachments.text_annotations if "report.pdf" in line),
        None,
    )
    assert annotation is not None
    assert "application/pdf" in annotation


async def test_document_message_extracts_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b"hello, world\n"
    document = SimpleNamespace(
        file_id="doc-id",
        file_name="note.txt",
        mime_type="text/plain",
        file_size=len(raw),
    )
    message = _make_message(document=document)
    bot = _make_bot_with_photo(raw)

    async def fake_extract(_raw: bytes, *, file_name: str) -> str:
        assert file_name == "note.txt"
        return "# Hello\n\nWorld."

    monkeypatch.setattr(
        "app.channels.telegram._attachments._extract_markdown_from_bytes",
        fake_extract,
    )

    attachments = await collect_attachments(message, bot)
    annotation = next(iter(attachments.text_annotations), "")
    assert "Extracted Markdown" in annotation
    assert "# Hello" in annotation


async def test_oversized_document_falls_back_to_metadata() -> None:
    document = SimpleNamespace(
        file_id="doc-id",
        file_name="huge.pdf",
        mime_type="application/pdf",
        file_size=99_999_999,
    )
    message = _make_message(document=document)
    attachments = await collect_attachments(message, AsyncMock())
    assert any("Too large" in line for line in attachments.text_annotations)


async def test_video_sticker_listed_as_unsupported() -> None:
    message = _make_message(
        video=SimpleNamespace(duration=3),
        sticker=SimpleNamespace(emoji="🐱"),
    )
    attachments = await collect_attachments(message, AsyncMock())
    assert "video" in attachments.unsupported
    assert "sticker" in attachments.unsupported


async def test_download_failure_is_swallowed_with_annotation() -> None:
    photo_size = SimpleNamespace(file_id="boom", file_size=10)
    message = _make_message(photo=[photo_size])
    bot = AsyncMock()
    bot.get_file = AsyncMock(side_effect=RuntimeError("telegram unavailable"))

    attachments = await collect_attachments(message, bot)

    assert attachments.images == []
    assert any("couldn't download" in line.lower() for line in attachments.text_annotations)
