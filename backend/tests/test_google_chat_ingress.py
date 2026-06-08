"""Tests for Google Chat ingress normalization into the shared turn runner."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.channels.google_chat import ingress
from app.channels.google_chat.attachments import GoogleChatAttachments
from app.channels.google_chat.channel import SURFACE_GOOGLE_CHAT
from app.turns.pipeline import ChatTurnInput


class _Provider:
    """Provider sentinel for ingress tests."""


class _Channel:
    """Channel sentinel for ingress tests."""

    surface = SURFACE_GOOGLE_CHAT


@pytest.mark.anyio
async def test_google_chat_message_event_submits_normalized_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Google Chat submits a ``ChatTurnInput`` without asserting provider internals."""
    user_id = uuid4()
    conversation_id = uuid4()
    workspace_id = uuid4()
    provider: Any = _Provider()
    channel: Any = _Channel()
    captured: dict[str, ChatTurnInput] = {}

    async def resolve_turn_target(_event: dict[str, Any]) -> ingress._TurnTarget:
        return ingress._TurnTarget(
            user_id=user_id,
            conversation_id=conversation_id,
            workspace_root=tmp_path,
            workspace_id=workspace_id,
            model_id="agent-sdk:anthropic/claude-opus-4-7",
            verbose_level=2,
        )

    async def create_placeholder(
        *,
        space_name: str,
        text: str,
        thread_name: str | None,
    ) -> str:
        assert space_name == "spaces/AAA"
        assert thread_name == "spaces/AAA/threads/BBB"
        assert text
        return "spaces/AAA/messages/placeholder"

    async def collect_attachments(_event: dict[str, Any]) -> GoogleChatAttachments:
        return GoogleChatAttachments(
            images=[{"data": "aW1hZ2U=", "media_type": "image/png"}],
            annotations=["[User sent a document: brief.md.]"],
        )

    async def run_turn(turn_input: ChatTurnInput) -> AsyncIterator[bytes]:
        captured["turn_input"] = turn_input
        yield b""

    monkeypatch.setattr(ingress, "_resolve_turn_target", resolve_turn_target)
    monkeypatch.setattr(
        ingress,
        "_resolve_provider",
        lambda model_id, workspace_root: (provider, "agent-sdk:anthropic/claude-opus-4-7"),
    )
    monkeypatch.setattr(ingress, "build_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(ingress, "create_message", create_placeholder)
    monkeypatch.setattr(ingress, "collect_attachments", collect_attachments)
    monkeypatch.setattr("app.channels.registry.resolve_channel", lambda _surface: channel)
    monkeypatch.setattr(ingress, "run_turn", run_turn)

    event = {
        "type": "MESSAGE",
        "space": {"name": "spaces/AAA"},
        "message": {
            "name": "spaces/AAA/messages/original",
            "text": "hello",
            "thread": {"name": "spaces/AAA/threads/BBB"},
        },
    }

    await ingress._handle_message_event(event)

    turn_input = captured["turn_input"]
    assert turn_input.conversation_id == conversation_id
    assert turn_input.user_id == user_id
    assert turn_input.question == "hello\n\n[User sent a document: brief.md.]"
    assert turn_input.provider is provider
    assert turn_input.channel is channel
    assert turn_input.workspace_root == tmp_path
    assert turn_input.tools == []
    assert turn_input.images == [{"data": "aW1hZ2U=", "media_type": "image/png"}]
    assert turn_input.log_tag == "GOOGLE_CHAT"
    assert turn_input.channel_message == {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "text": "hello",
        "surface": SURFACE_GOOGLE_CHAT,
        "model_id": "agent-sdk:anthropic/claude-opus-4-7",
        "metadata": {
            "space_name": "spaces/AAA",
            "thread_name": "spaces/AAA/threads/BBB",
            "message_name": "spaces/AAA/messages/placeholder",
            "verbose_level": 2,
        },
    }
