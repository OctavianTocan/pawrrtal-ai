"""Bounded LLM subcall helpers for internal turn-adjacent tasks."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from app.agents.types import AgentTool
from app.providers.base import StreamEvent
from app.providers.factory import resolve_llm


@dataclass(frozen=True, slots=True)
class LlmSubcall:
    """Model subcall request owned by the Turn Pipeline."""

    model_id: str
    question: str
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    workspace_root: Path
    tools: list[AgentTool]
    system_prompt: str
    history: list[dict[str, str]] | None = None


async def stream_llm_subcall(subcall: LlmSubcall) -> AsyncIterator[StreamEvent]:
    """Stream one internal LLM subcall through provider selection."""
    provider = resolve_llm(subcall.model_id, workspace_root=subcall.workspace_root)
    async for event in provider.stream(
        question=subcall.question,
        conversation_id=subcall.conversation_id,
        user_id=subcall.user_id,
        history=subcall.history,
        tools=subcall.tools,
        system_prompt=subcall.system_prompt,
    ):
        yield event
