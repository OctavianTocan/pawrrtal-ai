"""Tests for the bundled LCM conversation memory plugin backend."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.infrastructure.config import settings
from app.plugins.lcm_memory import backend as lcm_backend


def test_lcm_memory_backend_skips_compaction_when_lcm_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(settings, "lcm_enabled", False)
    monkeypatch.setattr(
        lcm_backend, "schedule_lcm_compaction", lambda **kwargs: calls.append(kwargs)
    )

    lcm_backend.LCMConversationMemoryBackend().schedule_compaction(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        model_id="gemini-2.5-flash",
    )

    assert calls == []


def test_lcm_memory_backend_schedules_compaction_when_lcm_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    conversation_id = uuid.uuid4()
    user_id = uuid.uuid4()
    monkeypatch.setattr(settings, "lcm_enabled", True)
    monkeypatch.setattr(
        lcm_backend, "schedule_lcm_compaction", lambda **kwargs: calls.append(kwargs)
    )

    lcm_backend.LCMConversationMemoryBackend().schedule_compaction(
        conversation_id=conversation_id,
        user_id=user_id,
        model_id="gemini-2.5-flash",
    )

    assert calls == [
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "model_id": "gemini-2.5-flash",
        }
    ]
