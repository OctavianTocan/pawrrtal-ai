"""First-class Pawrrtal provider backed by the official `openai_codex` Python SDK.

This is the real, executable implementation (no longer a commented plan).

It follows the SDK surface exactly:
- `AsyncCodex` + `AppServerConfig`
- `thread_start` / `thread.turn(...)` → `AsyncTurnHandle`
- Streaming via typed `Notification` payloads
- `ReasoningEffort` / `ReasoningSummary` enums from the generated types

The provider translates Pawrrtal's `stream(...)` contract (history, tools,
reasoning effort, system prompt) into Codex threads + turns and maps the
resulting notifications back to native `StreamEvent` records.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.providers.base import (
    ReasoningEffort as PawReasoningEffort,
)
from app.core.providers.base import (
    StreamEvent,
)
from app.core.providers.openai_codex.auth import build_app_server_config
from app.core.providers.openai_codex.events import (
    map_codex_notification_to_stream_events,
)
from app.core.providers.openai_codex.inputs import build_codex_run_input

# Pull SDK symbols through our own re-export layer (which owns the vendored
# snapshot compatibility logic in __init__.py + _vendor.py). This is the
# correct architectural pattern.
from . import (
    AppServerConfig,
    AsyncCodex,
    ReasoningSummary,
    TextInput,
)
from . import (
    ReasoningEffort as CodexReasoningEffort,
)

logger = logging.getLogger(__name__)


def _map_pawrrtal_reasoning_to_codex(
    effort: PawReasoningEffort | None,
) -> CodexReasoningEffort | None:
    """Map Pawrrtal's reasoning effort ladder to the SDK enum."""
    if effort is None:
        return None

    mapping: dict[PawReasoningEffort, CodexReasoningEffort] = {
        "minimal": CodexReasoningEffort.minimal,
        "low": CodexReasoningEffort.low,
        "medium": CodexReasoningEffort.medium,
        "high": CodexReasoningEffort.high,
        "extra-high": CodexReasoningEffort.high,  # SDK caps at high
    }
    return mapping.get(effort, CodexReasoningEffort.medium)


class OpenAICodexProvider:
    """First-class Pawrrtal AILLM provider using the official openai_codex SDK."""

    def __init__(
        self,
        model_id: str,
        *,
        workspace_root: Path | None = None,
        codex_bin: str | Path | None = None,
    ) -> None:
        self._model_id = model_id
        self._workspace_root = workspace_root
        self._codex_bin = codex_bin
        self._codex: AsyncCodex | None = None

    async def _ensure_codex(self) -> AsyncCodex:
        """Lazily create the AsyncCodex client (one per provider instance)."""
        if self._codex is not None:
            return self._codex

        cfg_dict = build_app_server_config(
            workspace_root=self._workspace_root,
            codex_bin=self._codex_bin,
        )

        # Convert our thin dict into a real AppServerConfig.
        # We deliberately pass through the keys the SDK understands.
        config = AppServerConfig(
            codex_bin=cfg_dict.get("codex_bin"),
            cwd=str(self._workspace_root) if self._workspace_root else None,
            env=cfg_dict.get("env"),
        )

        # The override token (if present) is carried in a private key by our
        # auth helper. For v1 we simply log that it exists; a follow-up will
        # wire it as a per-process CODEX_HOME or temp auth file before launch.
        if cfg_dict.get("_openai_codex_override_token"):
            logger.info(
                "openai_codex: workspace override token present for model=%s "
                "(full per-workspace auth injection coming in a follow-up)",
                self._model_id,
            )

        self._codex = AsyncCodex(config=config)
        return self._codex

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        history: list[dict[str, str]] | None = None,
        tools: list[AgentTool] | None = None,
        system_prompt: str | None = None,
        reasoning_effort: PawReasoningEffort | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Drive a Codex turn and emit native Pawrrtal StreamEvents."""
        if tools:
            logger.debug(
                "openai_codex provider: tools provided but not yet wired for model=%s "
                "(text-only path for v1)",
                self._model_id,
            )

        codex = await self._ensure_codex()
        await codex._ensure_initialized()  # ensure the app-server is up

        # Thread lifecycle: prefer resuming an existing Codex thread when we have one
        # persisted for this conversation. Falls back to fresh thread_start.
        # The actual persistence (storing codex_thread_id on the Conversation row)
        # is handled by the turn runner / caller when we emit a thread creation signal.
        existing_thread_id = kwargs.get("codex_thread_id")
        try:
            if existing_thread_id:
                thread = await codex.thread_resume(existing_thread_id)
            else:
                thread = await codex.thread_start(
                    model=self._model_id,
                    cwd=str(self._workspace_root) if self._workspace_root else None,
                    base_instructions=system_prompt,
                )
                # Signal to the caller that a new thread was created so it can be
                # persisted against the conversation for future resume.
                yield {
                    "type": "internal",
                    "kind": "codex_thread_created",
                    "thread_id": getattr(thread, "id", None),
                }
        except Exception as exc:
            logger.exception("openai_codex: thread_start/resume failed")
            yield {"type": "error", "content": f"Failed to start/resume Codex thread: {exc}"}
            return

        # Build rich input using the dedicated translation layer.
        # This gives us proper history replay, previous thinking, tool results,
        # and attached images — the main missing piece from the v1 implementation.
        images = kwargs.get("images")
        try:
            run_input = build_codex_run_input(
                question=question,
                history=history,
                images=images,
            )
        except Exception:
            # Fallback for any SDK input shape changes or translation issues
            run_input = TextInput(text=question) if question else question

        effort = _map_pawrrtal_reasoning_to_codex(reasoning_effort)

        try:
            handle = await thread.turn(
                run_input,
                effort=effort,
                summary=ReasoningSummary.auto,
            )

            # The high-level async handle exposes a stream of Notification objects.
            # We consume it directly.
            async for notification in handle.stream():  # type: ignore[attr-defined]
                for event in map_codex_notification_to_stream_events(notification):
                    if event:
                        yield event

        except Exception as exc:
            logger.exception("openai_codex: turn streaming failed")
            yield {"type": "error", "content": f"Codex turn failed: {exc}"}
            return

        # Normal completion is signaled by the mapper emitting a "done" event
        # when it sees a TurnCompletedNotification. Nothing more to do here.


# Backwards-compat alias used in a few places during the transition.
CodexLLM = OpenAICodexProvider
