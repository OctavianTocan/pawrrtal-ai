"""Tests for conversation title generation."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest

from app.conversations.title import (
    TITLE_GENERATION_SLOT,
    generate_conversation_title_text,
)
from app.providers.base import AILLM, StreamEvent
from app.providers.selection import ProviderSelection


class FakeTitleProvider:
    """Provider fake that records the title task request."""

    def __init__(self) -> None:
        self.questions: list[str] = []
        self.histories: list[list[dict[str, str]] | None] = []
        self.system_prompts: list[str | None] = []

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        history: list[dict[str, str]] | None = None,
        tools: object = None,
        system_prompt: str | None = None,
        reasoning_effort: object = None,
        images: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield a split title so aggregation is exercised."""
        self.questions.append(question)
        self.histories.append(history)
        self.system_prompts.append(system_prompt)
        yield {"type": "delta", "content": "Better"}
        yield {"type": "delta", "content": " Title"}


@pytest.mark.anyio
async def test_generate_conversation_title_text_uses_provider_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Title generation is provider-backed without importing provider SDKs."""
    provider = FakeTitleProvider()

    def _fake_require_provider(
        model_id: str,
        *,
        workspace_root: object = None,
    ) -> ProviderSelection:
        assert model_id == "test:title-model"
        assert workspace_root == Path("/workspace")
        return ProviderSelection(
            provider=cast(AILLM, provider),
            effective_model_id=model_id,
        )

    monkeypatch.setattr("app.conversations.title.require_provider", _fake_require_provider)

    title = await generate_conversation_title_text(
        first_message="How should this be organized?",
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        model_id="test:title-model",
        workspace_root=Path("/workspace"),
    )

    assert TITLE_GENERATION_SLOT == "conversation.title.generate"
    assert title == "Better Title"
    assert provider.histories == [[]]
    assert provider.system_prompts == [
        "You generate concise conversation titles. Return only the title text, "
        "with no quotes or explanation."
    ]
    assert "How should this be organized?" in provider.questions[0]
