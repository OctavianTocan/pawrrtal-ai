"""Telegram turn tests for provider-session handoff."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.telegram.bot import _run_llm_turn
from app.channels.telegram.handlers import TelegramTurnContext
from app.provider_sessions import ProviderSessionTurnState
from app.providers.selection import ProviderSelection


@pytest.mark.anyio
async def test_run_llm_turn_passes_prepared_provider_session(tmp_path: Path) -> None:
    """Telegram turns must use the selected provider's session preparation hook."""
    context = TelegramTurnContext(
        pawrrtal_user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        model_id="openai-codex:openai/gpt-5.5",
        thread_id=None,
    )
    workspace = SimpleNamespace(path=str(tmp_path), id=uuid.uuid4())
    message = SimpleNamespace(
        bot=AsyncMock(),
        chat=SimpleNamespace(id=7424950903),
        message_id=123,
        text="hello",
        caption=None,
        answer=AsyncMock(return_value=SimpleNamespace(message_id=999)),
    )
    captured: dict[str, Any] = {}

    async def fake_run_prepared_turn(prepared_turn: Any) -> AsyncIterator[bytes]:
        captured["turn_input"] = prepared_turn.turn_input
        if False:
            yield b""

    fake_session_maker = MagicMock()
    fake_session_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    fake_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.channels.telegram.bot.async_session_maker", new=fake_session_maker),
        patch("app.workspace.crud.get_default_workspace", AsyncMock(return_value=workspace)),
        patch(
            "app.channels.telegram.bot.resolve_provider_with_auto_clear",
            AsyncMock(
                return_value=(
                    ProviderSelection(
                        provider=MagicMock(),
                        effective_model_id="openai-codex:openai/gpt-5.5",
                    ),
                    None,
                )
            ),
        ),
        patch(
            "app.channels.telegram.bot.normalize_reasoning_and_notify",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.turns.pipeline.prepare.prepare_provider_session",
            new=AsyncMock(
                return_value=ProviderSessionTurnState(
                    kind="openai_codex",
                    session_id="thr_telegram",
                    fingerprint="hash_telegram",
                    stream_kwargs={"native_session_id": "thr_telegram"},
                    per_turn_context_kwarg="per_turn_context",
                    omit_history=True,
                    force_low_reasoning=True,
                ),
            ),
        ),
        patch("app.channels.telegram.bot.run_prepared_turn", new=fake_run_prepared_turn),
    ):
        await _run_llm_turn(message=cast(Any, message), context=context)

    assert captured["turn_input"].provider_session.session_id == "thr_telegram"
    assert captured["turn_input"].provider_session.fingerprint == "hash_telegram"
    assert captured["turn_input"].provider_session.force_low_reasoning is True
    assert "reply_to_message_id" not in captured["turn_input"].channel_message["metadata"]
    message.answer.assert_awaited_once()
    assert "reply_parameters" not in message.answer.await_args.kwargs
