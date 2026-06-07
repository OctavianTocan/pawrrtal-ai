"""Tests for provider-session hook preparation."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.provider_sessions import ProviderSessionTurnState
from app.providers.session_preparer import prepare_provider_session


class AsyncProvider:
    """Provider with a valid async session-preparation hook."""

    async def prepare_turn_session(
        self,
        *,
        conversation_id: UUID,
        workspace_root: Path | None,
        model_id: str | None,
        tools: object | None,
        reasoning_effort: object | None,
        question: str,
    ) -> ProviderSessionTurnState:
        del conversation_id, workspace_root, model_id, tools, reasoning_effort, question
        return ProviderSessionTurnState(kind="test", session_id="session-1")


class InvalidProvider:
    """Provider with an invalid hook result."""

    def prepare_turn_session(
        self,
        *,
        conversation_id: UUID,
        workspace_root: Path | None,
        model_id: str | None,
        tools: object | None,
        reasoning_effort: object | None,
        question: str,
    ) -> None:
        del conversation_id, workspace_root, model_id, tools, reasoning_effort, question


@pytest.mark.anyio
async def test_prepare_provider_session_accepts_async_hook_result() -> None:
    turn_state = await prepare_provider_session(
        AsyncProvider(),
        conversation_id=uuid4(),
        workspace_root=None,
        model_id=None,
        tools=None,
        reasoning_effort=None,
        question="hello",
    )

    assert turn_state == ProviderSessionTurnState(kind="test", session_id="session-1")


@pytest.mark.anyio
async def test_prepare_provider_session_rejects_invalid_hook_result() -> None:
    with pytest.raises(TypeError, match="prepare_turn_session"):
        await prepare_provider_session(
            InvalidProvider(),
            conversation_id=uuid4(),
            workspace_root=None,
            model_id=None,
            tools=None,
            reasoning_effort=None,
            question="hello",
        )
