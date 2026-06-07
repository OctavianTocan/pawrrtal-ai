"""Google Chat channel — ``/lcm`` status + ``/compact`` (lcm_commands).

Thin channel-local wrappers over the shared LCM services; these assert the
disabled-state messaging and the empty-conversation status read.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

import app.channels.google_chat.lcm_commands as lcm_module
from app.channels.google_chat.commands import CommandContext
from app.channels.google_chat.lcm_commands import lcm_status_text, run_compaction
from app.infrastructure.config import settings

pytestmark = pytest.mark.anyio


class _StubCompactionSession:
    """Async context manager that records whether compaction was committed."""

    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> _StubCompactionSession:
        return self

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


@asynccontextmanager
async def _unlocked_lcm(_conversation_id: uuid.UUID) -> AsyncIterator[None]:
    yield


async def test_lcm_status_disabled(
    monkeypatch: pytest.MonkeyPatch, command_ctx: CommandContext
) -> None:
    monkeypatch.setattr(settings, "lcm_enabled", False)
    text = await lcm_status_text(
        conversation_id=command_ctx.conversation.id, session=command_ctx.session
    )
    assert "disabled" in text.lower()


async def test_lcm_status_enabled_empty_conversation(
    monkeypatch: pytest.MonkeyPatch, command_ctx: CommandContext
) -> None:
    monkeypatch.setattr(settings, "lcm_enabled", True)
    text = await lcm_status_text(
        conversation_id=command_ctx.conversation.id, session=command_ctx.session
    )
    assert "LCM status" in text
    assert "0 messages" in text


async def test_run_compaction_disabled(
    monkeypatch: pytest.MonkeyPatch, command_ctx: CommandContext
) -> None:
    monkeypatch.setattr(settings, "lcm_enabled", False)
    text = await run_compaction(
        conversation_id=command_ctx.conversation.id, user_id=command_ctx.user_id, model_id="x"
    )
    assert "disabled" in text.lower()


async def test_run_compaction_commits_successful_compaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def compacted(
        _session: object,
        *,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        model_id: str,
        fresh_tail_count: int,
        max_chunk_tokens: int,
    ) -> bool:
        assert isinstance(conversation_id, uuid.UUID)
        assert isinstance(user_id, uuid.UUID)
        assert model_id
        assert fresh_tail_count >= 0
        assert max_chunk_tokens > 0
        return True

    session = _StubCompactionSession()
    monkeypatch.setattr(settings, "lcm_enabled", True)
    monkeypatch.setattr(lcm_module, "acquire_lcm_lock", _unlocked_lcm)
    monkeypatch.setattr(lcm_module, "async_session_maker", lambda: session)
    monkeypatch.setattr(lcm_module, "compact_leaf_if_needed", compacted)

    text = await run_compaction(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        model_id="litellm:openai/gpt-4o-mini",
    )

    assert session.committed
    assert "Compacted" in text
