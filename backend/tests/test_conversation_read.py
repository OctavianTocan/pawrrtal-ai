"""ConversationRead.model_id validator behaviour with the strict /
permissive feature flag."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.infrastructure.config import settings
from app.providers.catalog import default_model
from app.schemas import ChatRequest, ConversationRead


def _read_row(model_id: str | None) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "user_id": uuid4(),
        "title": "x",
        "created_at": now,
        "updated_at": now,
        "is_archived": False,
        "is_flagged": False,
        "is_unread": False,
        "status": "active",
        "model_id": model_id,
        "labels": [],
        "project_id": None,
    }


def test_canonical_value_passes_through_unchanged() -> None:
    canonical = default_model().id
    read = ConversationRead.model_validate(_read_row(canonical))
    assert read.model_id == canonical


def test_strict_mode_rejects_bare_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "strict_conversation_read_validation", True)
    with pytest.raises(ValidationError):
        ConversationRead.model_validate(_read_row("gemini-3-flash-preview"))


def test_permissive_mode_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "strict_conversation_read_validation", False)
    with caplog.at_level(logging.WARNING, logger="app.schemas"):
        read = ConversationRead.model_validate(_read_row("gemini-3-flash-preview"))
    assert read.model_id == default_model().id
    assert any("CONVERSATION_READ_FALLBACK" in r.message for r in caplog.records)


def test_canonicalises_bare_form_on_input() -> None:
    """ChatRequest accepts the vendor-only form and rewrites to canonical."""
    req = ChatRequest(
        question="hi",
        conversation_id=uuid4(),
        model_id="anthropic/claude-sonnet-4-6",
        reasoning_effort="extra-high",
    )
    assert req.model_id == "agent-sdk:anthropic/claude-sonnet-4-6"
    assert req.reasoning_effort == "extra-high"


def test_rejects_bare_on_input() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(
            question="hi",
            conversation_id=uuid4(),
            model_id="claude-sonnet-4-6",
        )
