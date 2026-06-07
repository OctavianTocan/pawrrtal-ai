"""Google Chat channel — inbound media ingestion (attachments).

Images become base64 vision input; documents are extracted to Markdown; audio
and Drive files become a metadata annotation only; a missing download reference
is annotated rather than crashing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.google_chat import attachments as attachments_module
from app.channels.google_chat.attachments import collect_attachments
from app.channels.google_chat.messages import attachments_of
from tests.channels.google_chat.helpers import event_with_attachment

pytestmark = pytest.mark.anyio


def test_attachments_of_reads_repeated_field() -> None:
    att = {"contentName": "a.png", "contentType": "image/png"}
    assert attachments_of(event_with_attachment(att)) == [att]


async def test_collect_image_becomes_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        attachments_module, "download_attachment", AsyncMock(return_value=b"\x89PNGdata")
    )
    event = event_with_attachment(
        {
            "contentName": "shot.png",
            "contentType": "image/png",
            "source": "UPLOADED_CONTENT",
            "attachmentDataRef": {"resourceName": "spaces/A/messages/M/attachments/1"},
        }
    )
    out = await collect_attachments(event)
    assert len(out.images) == 1
    assert out.images[0]["media_type"] == "image/png"
    assert out.images[0]["data"]


async def test_collect_unsupported_image_mime_annotates(monkeypatch: pytest.MonkeyPatch) -> None:
    download_spy = AsyncMock(return_value=b"heic")
    monkeypatch.setattr(attachments_module, "download_attachment", download_spy)
    event = event_with_attachment(
        {
            "contentName": "phone.heic",
            "contentType": "image/heic",
            "source": "UPLOADED_CONTENT",
            "attachmentDataRef": {"resourceName": "spaces/A/messages/M/attachments/1"},
        }
    )

    out = await collect_attachments(event)

    assert out.images == []
    assert any("unsupported image" in note for note in out.annotations)
    download_spy.assert_not_awaited()


async def test_collect_total_download_budget_skips_later_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_download(*_args: object, max_bytes: int, **_kwargs: object) -> bytes:
        return b"x" * max_bytes

    monkeypatch.setattr(attachments_module, "_MAX_TOTAL_DOWNLOAD_BYTES", 3)
    monkeypatch.setattr(attachments_module, "download_attachment", _fake_download)
    event = event_with_attachment(
        {
            "contentName": "first.png",
            "contentType": "image/png",
            "source": "UPLOADED_CONTENT",
            "attachmentDataRef": {"resourceName": "spaces/A/messages/M/attachments/1"},
        }
    )
    event["chat"]["messagePayload"]["message"]["attachment"].append(
        {
            "contentName": "second.png",
            "contentType": "image/png",
            "source": "UPLOADED_CONTENT",
            "attachmentDataRef": {"resourceName": "spaces/A/messages/M/attachments/2"},
        }
    )

    out = await collect_attachments(event)

    assert len(out.images) == 1
    assert any("processing limits" in note for note in out.annotations)


async def test_collect_attachment_failure_becomes_annotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_download(*_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError("download timeout")

    monkeypatch.setattr(attachments_module, "download_attachment", _raise_download)
    event = event_with_attachment(
        {
            "contentName": "shot.png",
            "contentType": "image/png",
            "source": "UPLOADED_CONTENT",
            "attachmentDataRef": {"resourceName": "spaces/A/messages/M/attachments/1"},
        }
    )

    out = await collect_attachments(event)

    assert out.images == []
    assert any("could not process" in note for note in out.annotations)


async def test_collect_attachment_count_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(attachments_module, "download_attachment", AsyncMock(return_value=b"x"))
    event = event_with_attachment(
        {
            "contentName": "one.ogg",
            "contentType": "audio/ogg",
            "source": "UPLOADED_CONTENT",
            "attachmentDataRef": {"resourceName": "spaces/A/messages/M/attachments/1"},
        }
    )
    event["chat"]["messagePayload"]["message"]["attachment"] = [
        {
            "contentName": f"{index}.ogg",
            "contentType": "audio/ogg",
            "source": "UPLOADED_CONTENT",
            "attachmentDataRef": {"resourceName": f"spaces/A/messages/M/attachments/{index}"},
        }
        for index in range(5)
    ]

    out = await collect_attachments(event)

    assert sum("voice/audio" in note for note in out.annotations) == 4
    assert any("Skipped 1 additional" in note for note in out.annotations)


async def test_collect_audio_is_annotation_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(attachments_module, "download_attachment", AsyncMock(return_value=b"audio"))
    event = event_with_attachment(
        {
            "contentName": "voice.ogg",
            "contentType": "audio/ogg",
            "source": "UPLOADED_CONTENT",
            "attachmentDataRef": {"resourceName": "spaces/A/messages/M/attachments/2"},
        }
    )
    out = await collect_attachments(event)
    assert out.images == []
    assert any("voice/audio" in note for note in out.annotations)


async def test_collect_drive_file_is_annotation(monkeypatch: pytest.MonkeyPatch) -> None:
    download_spy = AsyncMock(return_value=b"x")
    monkeypatch.setattr(attachments_module, "download_attachment", download_spy)
    event = event_with_attachment(
        {
            "contentName": "doc.gdoc",
            "contentType": "application/vnd.google-apps.document",
            "source": "DRIVE_FILE",
            "driveDataRef": {"driveFileId": "abc"},
        }
    )
    out = await collect_attachments(event)
    assert any("Drive file" in note for note in out.annotations)
    download_spy.assert_not_awaited()


async def test_collect_document_inlines_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        attachments_module, "download_attachment", AsyncMock(return_value=b"%PDF...")
    )

    async def _fake_extract(raw_bytes: bytes, *, file_name: str) -> str:
        return "# Heading\nbody text"

    monkeypatch.setattr(attachments_module, "_extract_markdown", _fake_extract)
    event = event_with_attachment(
        {
            "contentName": "report.pdf",
            "contentType": "application/pdf",
            "source": "UPLOADED_CONTENT",
            "attachmentDataRef": {"resourceName": "spaces/A/messages/M/attachments/3"},
        }
    )
    out = await collect_attachments(event)
    assert out.images == []
    assert any("Extracted Markdown" in note and "Heading" in note for note in out.annotations)


async def test_collect_missing_resource_annotates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(attachments_module, "download_attachment", AsyncMock(return_value=b"x"))
    event = event_with_attachment(
        {"contentName": "weird", "contentType": "image/png", "source": "UPLOADED_CONTENT"}
    )
    out = await collect_attachments(event)
    assert out.images == []
    assert any("no downloadable reference" in note for note in out.annotations)
