"""Tests for the multimodal-image plumbing on ``ChatRequest`` (PR 09)."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.schemas import ChatImageInput, ChatRequest


class TestChatImageInput:
    def test_default_media_type(self) -> None:
        img = ChatImageInput(data="abc")
        assert img.media_type == "image/png"

    @pytest.mark.parametrize(
        "media_type",
        ["image/png", "image/jpeg", "image/gif", "image/webp"],
    )
    def test_accepts_supported_mime_types(self, media_type: str) -> None:
        img = ChatImageInput(data="abc", media_type=media_type)
        assert img.media_type == media_type

    def test_rejects_unsupported_mime_type(self) -> None:
        with pytest.raises(ValidationError):
            ChatImageInput(data="abc", media_type="image/svg+xml")


class TestChatRequest:
    def test_images_default_to_none(self) -> None:
        req = ChatRequest(question="hi", conversation_id=uuid.uuid4())
        assert req.images is None

    def test_accepts_image_list(self) -> None:
        req = ChatRequest(
            question="what is this?",
            conversation_id=uuid.uuid4(),
            images=[
                ChatImageInput(data="abc", media_type="image/png"),
                ChatImageInput(data="def", media_type="image/jpeg"),
            ],
        )
        assert req.images is not None
        assert len(req.images) == 2
        assert req.images[0].data == "abc"
