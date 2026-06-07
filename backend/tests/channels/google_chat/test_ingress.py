"""Google Chat channel — pull loop + click-space resolution (ingress).

A card click carries its space under ``buttonClickedPayload`` (not
``messagePayload``), and the pull loop must acknowledge a message BEFORE its
(potentially slow) turn runs — otherwise Pub/Sub redelivers mid-turn and the
user gets a duplicate reply.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.channels.google_chat.attachments import GoogleChatAttachments
from app.channels.google_chat.messages import space_name
from tests.channels.google_chat.helpers import SPACE, addon_event, click_event, pubsub_envelope

pytestmark = pytest.mark.anyio


def test_space_name_resolved_from_button_click() -> None:
    # A card click carries its space under buttonClickedPayload, not messagePayload.
    event = click_event(function="gchat_set_verbose", value="2")
    assert space_name(event) == SPACE


async def test_pull_once_acks_before_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    # H1 regression guard: messages must be acked BEFORE their (potentially
    # slow) turns run, or Pub/Sub redelivers mid-turn → duplicate replies.
    import app.channels.google_chat.ingress as ingress_module

    order: list[str] = []

    async def _fake_pull(**_kwargs: Any) -> list[dict[str, Any]]:
        return [pubsub_envelope(addon_event())]

    async def _fake_ack(**_kwargs: Any) -> bool:
        order.append("ack")
        return True

    async def _fake_handle(_event: dict[str, Any] | None) -> None:
        order.append("handle")

    monkeypatch.setattr(ingress_module, "pull_messages", _fake_pull)
    monkeypatch.setattr(ingress_module, "acknowledge", _fake_ack)
    monkeypatch.setattr(ingress_module, "_maybe_handle", _fake_handle)

    assert await ingress_module._pull_once() is True
    assert order == ["ack", "handle"]


async def test_pull_once_skips_handling_when_ack_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.channels.google_chat.ingress as ingress_module

    order: list[str] = []

    async def _fake_pull(**_kwargs: Any) -> list[dict[str, Any]]:
        return [pubsub_envelope(addon_event())]

    async def _fake_ack(**_kwargs: Any) -> bool:
        order.append("ack")
        return False

    async def _fake_handle(_event: dict[str, Any] | None) -> None:
        order.append("handle")

    monkeypatch.setattr(ingress_module, "pull_messages", _fake_pull)
    monkeypatch.setattr(ingress_module, "acknowledge", _fake_ack)
    monkeypatch.setattr(ingress_module, "_maybe_handle", _fake_handle)

    assert await ingress_module._pull_once() is False
    assert order == ["ack"]


async def test_message_turn_forwards_google_chat_overrides_and_hooks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.channels.google_chat.ingress as ingress_module

    captured: dict[str, Any] = {}

    async def _fake_hook(_ctx: object) -> None:
        return None

    target = ingress_module._TurnTarget(
        user_id=uuid4(),
        conversation_id=uuid4(),
        workspace_root=tmp_path,
        workspace_id=uuid4(),
        model_id="google-ai:google/gemini-3-flash-preview",
        verbose_level=2,
        reasoning_effort="high",
    )

    async def _fake_resolve_target(_event: dict[str, Any]) -> object:
        return target

    async def _fake_create_message(**_kwargs: Any) -> str:
        return f"{SPACE}/messages/PLACEHOLDER"

    async def _fake_collect(_event: dict[str, Any]) -> GoogleChatAttachments:
        return GoogleChatAttachments()

    async def _fake_run_turn(turn_input: object) -> AsyncIterator[bytes]:
        captured["turn_input"] = turn_input
        yield b""

    monkeypatch.setattr(ingress_module, "_resolve_turn_target", _fake_resolve_target)
    monkeypatch.setattr(
        ingress_module, "_resolve_provider", lambda *_args: (object(), target.model_id)
    )
    monkeypatch.setattr(ingress_module, "build_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(ingress_module, "create_message", _fake_create_message)
    monkeypatch.setattr(ingress_module, "collect_attachments", _fake_collect)
    monkeypatch.setattr(ingress_module, "build_pre_turn_hooks", lambda: [_fake_hook])
    monkeypatch.setattr(ingress_module, "run_turn", _fake_run_turn)

    await ingress_module._handle_message_event(addon_event(text="hello"))

    turn_input = captured["turn_input"]
    assert turn_input.verbose_level == 2
    assert turn_input.reasoning_effort == "high"
    assert turn_input.pre_turn_hooks == [_fake_hook]


async def test_message_turn_clears_unsupported_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.channels.google_chat.ingress as ingress_module

    captured: dict[str, Any] = {}
    target = ingress_module._TurnTarget(
        user_id=uuid4(),
        conversation_id=uuid4(),
        workspace_root=tmp_path,
        workspace_id=uuid4(),
        model_id="litellm:openai/gpt-4o",
        verbose_level=1,
        reasoning_effort="high",
    )

    async def _fake_resolve_target(_event: dict[str, Any]) -> object:
        return target

    async def _fake_create_message(**_kwargs: Any) -> str:
        return f"{SPACE}/messages/PLACEHOLDER"

    async def _fake_collect(_event: dict[str, Any]) -> GoogleChatAttachments:
        return GoogleChatAttachments()

    async def _fake_run_turn(turn_input: object) -> AsyncIterator[bytes]:
        captured["turn_input"] = turn_input
        yield b""

    monkeypatch.setattr(ingress_module, "_resolve_turn_target", _fake_resolve_target)
    monkeypatch.setattr(
        ingress_module, "_resolve_provider", lambda *_args: (object(), target.model_id)
    )
    monkeypatch.setattr(ingress_module, "build_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(ingress_module, "create_message", _fake_create_message)
    monkeypatch.setattr(ingress_module, "collect_attachments", _fake_collect)
    monkeypatch.setattr(ingress_module, "run_turn", _fake_run_turn)

    await ingress_module._handle_message_event(addon_event(text="hello"))

    assert captured["turn_input"].reasoning_effort is None
