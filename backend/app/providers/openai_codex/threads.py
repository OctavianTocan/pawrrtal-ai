"""Codex native thread lifecycle helpers."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast

from app.agents.types import AgentTool
from app.channels._turn_runtime_context import system_prompt_for_turn
from app.provider_sessions import (
    ProviderSessionTurnState,
    load_provider_session,
    persist_provider_session,
)
from app.providers.base import ReasoningEffort
from app.providers.openai_codex.dynamic_tools import dynamic_tool_fingerprint
from app.providers.openai_codex.prompting import (
    CODEX_DEVELOPER_INSTRUCTIONS,
    should_use_lightweight_codex_prompt,
)

logger = logging.getLogger(__name__)
PROVIDER_SESSION_KIND = "openai_codex"


class _OpenAICodexProviderLike(Protocol):
    """Provider surface this module needs without importing the SDK-backed class."""

    model_id: str


@dataclass(frozen=True)
class CodexThreadState:
    """Reusable Codex thread decision for one Pawrrtal turn."""

    thread_id: str | None
    prompt_hash: str | None
    lightweight_prompt: bool = False

    def to_turn_state(self) -> ProviderSessionTurnState:
        """Return the generic turn state consumed by core orchestration."""
        stream_kwargs = {"codex_thread_id": self.thread_id} if self.thread_id else {}
        return ProviderSessionTurnState(
            kind=PROVIDER_SESSION_KIND,
            session_id=self.thread_id,
            fingerprint=self.prompt_hash,
            stream_kwargs=stream_kwargs,
            per_turn_context_kwarg="per_turn_context",
            omit_history=self.prompt_hash is not None,
            force_low_reasoning=self.lightweight_prompt,
        )


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
    if not _is_openai_codex_provider(provider):
        return CodexThreadState(thread_id=None, prompt_hash=None)
    codex_provider = cast(_OpenAICodexProviderLike, provider)

    lightweight_prompt = should_use_lightweight_codex_prompt(question)
    system_prompt = system_prompt_for_turn(
        workspace_root,
        model_id=model_id,
        tools=tools,
        extra_context=None,
        reasoning_effort=reasoning_effort,
    )
    prompt_hash = codex_thread_prompt_hash(
        model_id=codex_provider.model_id,
        workspace_root=workspace_root,
        system_prompt=system_prompt,
        developer_instructions=CODEX_DEVELOPER_INSTRUCTIONS,
        tool_fingerprint=dynamic_tool_fingerprint(tools),
    )
    existing = await load_provider_session(conversation_id)
    if (
        existing
        and existing.kind == PROVIDER_SESSION_KIND
        and existing.session_id
        and existing.fingerprint == prompt_hash
    ):
        return CodexThreadState(
            thread_id=existing.session_id,
            prompt_hash=prompt_hash,
            lightweight_prompt=lightweight_prompt,
        )
    if existing and existing.kind == PROVIDER_SESSION_KIND and existing.session_id:
        logger.info(
            "openai_codex: discarding stale thread for conversation=%s reason=prompt_hash_changed",
            conversation_id,
        )
        await persist_provider_session(
            conversation_id,
            kind=PROVIDER_SESSION_KIND,
            session_id=None,
            fingerprint=prompt_hash,
        )
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
    tool_fingerprint: str = "",
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
    digest.update(b"\0")
    digest.update(tool_fingerprint.encode("utf-8"))
    return digest.hexdigest()


def _is_openai_codex_provider(provider: object) -> bool:
    """Return whether ``provider`` is the concrete Codex provider."""
    provider_cls = provider.__class__
    return (
        provider_cls.__name__ == "OpenAICodexProvider"
        and provider_cls.__module__ == "app.providers.openai_codex.provider"
    )


__all__ = [
    "CODEX_DEVELOPER_INSTRUCTIONS",
    "PROVIDER_SESSION_KIND",
    "CodexThreadState",
    "codex_thread_prompt_hash",
    "dynamic_tool_fingerprint",
    "ensure_codex_thread_id",
    "ensure_codex_thread_state",
]
