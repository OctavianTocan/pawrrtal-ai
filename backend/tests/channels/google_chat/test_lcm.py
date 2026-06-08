"""Google Chat channel — ``/lcm`` status + ``/compact`` (lcm_commands).

Thin channel-local wrappers over the shared LCM services; these assert the
disabled-state messaging and the empty-conversation status read.
"""

from __future__ import annotations

import pytest

from app.channels.google_chat.commands import CommandContext
from app.channels.google_chat.lcm_commands import lcm_status_text, run_compaction
from app.infrastructure.config import settings

pytestmark = pytest.mark.anyio


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
