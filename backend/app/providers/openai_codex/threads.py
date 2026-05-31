"""Codex native thread lifecycle helpers."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from app.agents.types import AgentTool
from app.channels._turn_runtime_context import system_prompt_for_turn
from app.channels.turn_runner import load_codex_thread_state, persist_codex_thread_id
from app.providers.base import ReasoningEffort
from app.providers.openai_codex.prompting import (
    CODEX_DEVELOPER_INSTRUCTIONS,
    CODEX_LIGHT_SYSTEM_PROMPT,
    should_use_lightweight_codex_prompt,
)
from app.providers.openai_codex.provider import (
    OpenAICodexProvider,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodexThreadState:
    """Reusable Codex thread decision for one Pawrrtal turn."""

    thread_id: str | None
    prompt_hash: str | None
    lightweight_prompt: bool = False


async def ensure_codex_thread_id(
    *,
    conversation_id: uuid.UUID,
    provider: object,
    workspace_root: Path | None,
    model_id: str | None,
    tools: list[AgentTool] | None,
    reasoning_effort: ReasoningEffort | None,
    question: str = "",
) -> str | None:
    """Return a persisted native Codex thread id if it is still reusable."""
    state = await ensure_codex_thread_state(
        conversation_id=conversation_id,
        provider=provider,
        workspace_root=workspace_root,
        model_id=model_id,
        tools=tools,
        reasoning_effort=reasoning_effort,
        question=question,
    )
    return state.thread_id


async def ensure_codex_thread_state(
    *,
    conversation_id: uuid.UUID,
    provider: object,
    workspace_root: Path | None,
    model_id: str | None,
    tools: list[AgentTool] | None,
    reasoning_effort: ReasoningEffort | None,
    question: str = "",
) -> CodexThreadState:
    """Return a persisted native Codex thread id, creating one if needed.

    Pawrrtal stores chat messages for UI/audit, but the Codex SDK thread is
    the source of continuity for native Codex turns. Empty prewarmed SDK
    threads do not have a materialized rollout yet, so this helper only
    validates existing state. Fresh threads are opened by the first real turn.
    """
    if not isinstance(provider, OpenAICodexProvider):
        return CodexThreadState(thread_id=None, prompt_hash=None)

    lightweight_prompt = should_use_lightweight_codex_prompt(question)
    system_prompt = (
        CODEX_LIGHT_SYSTEM_PROMPT
        if lightweight_prompt
        else system_prompt_for_turn(
            workspace_root,
            model_id=model_id,
            tools=tools,
            extra_context=None,
            reasoning_effort=reasoning_effort,
        )
    )
    prompt_hash = codex_thread_prompt_hash(
        model_id=provider.model_id,
        workspace_root=workspace_root,
        system_prompt=system_prompt,
        developer_instructions=CODEX_DEVELOPER_INSTRUCTIONS,
    )
    existing = await load_codex_thread_state(conversation_id)
    if existing and existing[0] and existing[1] == prompt_hash:
        return CodexThreadState(
            thread_id=existing[0],
            prompt_hash=prompt_hash,
            lightweight_prompt=lightweight_prompt,
        )
    if existing and existing[0]:
        logger.info(
            "openai_codex: discarding stale thread for conversation=%s reason=prompt_hash_changed",
            conversation_id,
        )
        await persist_codex_thread_id(conversation_id, None, prompt_hash)
    return CodexThreadState(
        thread_id=None,
        prompt_hash=prompt_hash,
        lightweight_prompt=lightweight_prompt,
    )


def codex_thread_prompt_hash(
    *,
    model_id: str,
    workspace_root: Path | None,
    system_prompt: str | None,
    developer_instructions: str = "",
) -> str:
    """Return the fingerprint that decides whether a Codex thread is reusable."""
    digest = sha256()
    digest.update(model_id.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(workspace_root or "").encode("utf-8"))
    digest.update(b"\0")
    digest.update((system_prompt or "").encode("utf-8"))
    digest.update(b"\0")
    digest.update(developer_instructions.encode("utf-8"))
    return digest.hexdigest()


__all__ = [
    "CODEX_DEVELOPER_INSTRUCTIONS",
    "CODEX_LIGHT_SYSTEM_PROMPT",
    "CodexThreadState",
    "codex_thread_prompt_hash",
    "ensure_codex_thread_id",
    "ensure_codex_thread_state",
]
