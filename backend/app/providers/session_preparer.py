"""Provider-session preparation without provider-specific imports."""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol, cast

from app.agents.types import AgentTool
from app.provider_sessions import ProviderSessionTurnState
from app.providers.base import ReasoningEffort


class SupportsProviderSession(Protocol):
    """Optional provider hook for preparing opaque session continuity."""

    def prepare_turn_session(
        self,
        *,
        conversation_id: uuid.UUID,
        workspace_root: Path | None,
        model_id: str | None,
        tools: list[AgentTool] | None,
        reasoning_effort: ReasoningEffort | None,
        question: str,
    ) -> ProviderSessionTurnState | Awaitable[ProviderSessionTurnState]:
        """Return provider-owned session behavior for the next stream call."""
        ...


async def prepare_provider_session(
    provider: object,
    *,
    conversation_id: uuid.UUID,
    workspace_root: Path | None,
    model_id: str | None,
    tools: list[AgentTool] | None,
    reasoning_effort: ReasoningEffort | None,
    question: str,
) -> ProviderSessionTurnState:
    """Ask a provider for opaque session state when it supports the hook."""
    prepare = getattr(provider, "prepare_turn_session", None)
    if not callable(prepare):
        return ProviderSessionTurnState()
    typed_prepare = cast(
        Callable[..., ProviderSessionTurnState | Awaitable[ProviderSessionTurnState]],
        prepare,
    )
    result = typed_prepare(
        conversation_id=conversation_id,
        workspace_root=workspace_root,
        model_id=model_id,
        tools=tools,
        reasoning_effort=reasoning_effort,
        question=question,
    )
    if inspect.isawaitable(result):
        return await result
    return result
