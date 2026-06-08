"""Bounded LLM subcall helpers for internal turn-adjacent tasks."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from app.agents.types import AgentTool
from app.providers.base import ReasoningEffort, StreamEvent
from app.providers.factory import resolve_llm


@dataclass(frozen=True, slots=True)
class LlmSubcall:
    """Model subcall request owned by the Turn Pipeline."""

    model_id: str
    question: str
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    tools: list[AgentTool]
    system_prompt: str
    workspace_root: Path | None = None
    history: list[dict[str, str]] | None = None


async def stream_llm_subcall(subcall: LlmSubcall) -> AsyncIterator[StreamEvent]:
    """Stream one internal LLM subcall through provider selection."""
    if subcall.workspace_root is None:
        provider = resolve_llm(subcall.model_id)
    else:
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


@dataclass(frozen=True, slots=True)
class CodexImageSubcall:
    """Codex image-generation subcall request owned by the Turn Pipeline."""

    prompt: str
    model_id: str
    workspace_root: Path | None
    system_prompt: str
    reasoning_effort: ReasoningEffort


async def stream_codex_image_subcall(subcall: CodexImageSubcall) -> AsyncIterator[StreamEvent]:
    """Stream one Codex image-generation subcall through provider selection."""
    model_id = _codex_model_id(subcall.model_id)
    provider = resolve_llm(model_id, workspace_root=subcall.workspace_root)
    async for event in provider.stream(
        question=subcall.prompt,
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        tools=[],
        system_prompt=subcall.system_prompt,
        reasoning_effort=subcall.reasoning_effort,
    ):
        yield event


def _codex_model_id(model_id: str) -> str:
    """Return a canonical OpenAI Codex model id."""
    if ":" in model_id:
        return model_id
    return f"openai-codex:openai/{model_id}"
