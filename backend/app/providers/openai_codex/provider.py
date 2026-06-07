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
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.agents.types import AgentTool
from app.provider_sessions import ProviderSessionTurnState
from app.providers.base import (
    ReasoningEffort as PawReasoningEffort,
)
from app.providers.base import (
    StreamEvent,
)
from app.providers.openai_codex.auth import build_app_server_config
from app.providers.openai_codex.dynamic_tools import (
    CodexDynamicToolBridge,
    start_codex_thread,
    thread_start_payload,
)
from app.providers.openai_codex.inputs import build_codex_run_input
from app.providers.openai_codex.prompting import CODEX_DEVELOPER_INSTRUCTIONS
from app.providers.openai_codex.telemetry import log_codex_phase
from app.providers.openai_codex.threads import ensure_codex_thread_state
from app.providers.openai_codex.turn_stream import stream_codex_turn

# Make sure the vendored SDK is on sys.path before we statically import from
# it. ``_vendor.ensure_openai_codex_available`` injects the vendored source
# path when the published wheels aren't installed; calling it at import time
# keeps the symbols below resolvable at runtime. (mypy sees them via
# ``mypy_path`` in pyproject.toml, which points at the same source tree.)
from ._vendor import ensure_openai_codex_available

try:
    ensure_openai_codex_available()
except RuntimeError as exc:
    raise ImportError(str(exc)) from exc

# Import the SDK symbols directly from the vendored / installed package.
# We deliberately bypass the local ``__init__.__getattr__`` shim here: that
# shim returns ``Any`` to keep the package import cheap, which defeats type
# checking inside this module. The shim still serves the public Pawrrtal
# surface (``from app.providers.openai_codex import OpenAICodexProvider``).
from openai_codex import AppServerConfig, AsyncCodex, TextInput
from openai_codex.generated.v2_all import ReasoningEffort as CodexReasoningEffort

logger = logging.getLogger(__name__)

_DEFAULT_REASONING_SUMMARY: Any | None = None


def _get_default_reasoning_summary() -> Any:
    """Lazily build a validated ReasoningSummary('auto') on first use.

    ReasoningSummary is a Pydantic RootModel (see
    vendor/codex/sdk/python/src/openai_codex/generated/v2_all.py:2685).
    Canonical SDK usage is ReasoningSummary.model_validate('auto')
    (see vendor/codex/sdk/python/examples/12_turn_params_kitchen_sink/async.py).

    Lazy so an SDK drift in a future cli-bin bump surfaces as a clear
    runtime error on a Codex turn — not as a backend startup crash that
    takes down every other provider.
    """
    # Module-scope cache for the singleton ``ReasoningSummary("auto")`` so
    # we only validate it once per process. A plain global is the simplest
    # fit for "lazy import + cache"; refactoring to a closure or class
    # singleton would not change behaviour.
    global _DEFAULT_REASONING_SUMMARY  # noqa: PLW0603
    if _DEFAULT_REASONING_SUMMARY is None:
        from . import ReasoningSummary  # noqa: PLC0415 — lazy by design

        _DEFAULT_REASONING_SUMMARY = ReasoningSummary.model_validate("auto")
    return _DEFAULT_REASONING_SUMMARY


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


def _build_run_input_for_turn(
    *,
    question: str,
    history: list[dict[str, str]] | None,
    codex_thread_id: str | None,
    per_turn_context: str | None,
    images: list[dict[str, str]] | None,
) -> Any:
    """Build SDK input for one Codex turn, falling back across SDK drift."""
    try:
        return build_codex_run_input(
            question=question,
            history=[] if codex_thread_id else history,
            per_turn_context=per_turn_context,
            images=images,
        )
    except Exception:
        return TextInput(text=question) if question else question


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
        self._dynamic_tool_bridge = CodexDynamicToolBridge()

    @property
    def model_id(self) -> str:
        """Native Codex model id used when creating or resuming SDK threads."""
        return self._model_id

    async def prepare_turn_session(
        self,
        *,
        conversation_id: uuid.UUID,
        workspace_root: Path | None,
        model_id: str | None,
        tools: list[AgentTool] | None,
        reasoning_effort: PawReasoningEffort | None,
        question: str,
    ) -> ProviderSessionTurnState:
        """Prepare generic session continuity for the turn runner."""
        state = await ensure_codex_thread_state(
            conversation_id=conversation_id,
            provider=self,
            workspace_root=workspace_root,
            model_id=model_id,
            tools=tools,
            reasoning_effort=reasoning_effort,
            question=question,
        )
        return state.to_turn_state()

    async def close(self) -> None:
        """Close the owned Codex app-server client if it has been started."""
        if self._codex is None:
            return
        codex = self._codex
        self._codex = None
        await codex.close()

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
        self._install_deny_all_approval_handler()
        return self._codex

    def _install_deny_all_approval_handler(self) -> None:
        """Install the deny-all approval handler on the underlying sync client.

        AsyncCodex / AsyncAppServerClient (vendored 0.131.0a4) do not accept
        an approval_handler kwarg, so we reach into the wrapped sync client
        to override its default. Tracked in bean pawrrtal-roi0 (tool bridge)
        which will replace this with an agent-loop-aware handler.
        """
        if self._codex is None:
            return
        client = getattr(self._codex, "_client", None)
        sync = getattr(client, "_sync", None)
        if sync is None:
            logger.warning(
                "openai_codex: could not reach sync client to install approval handler "
                "— falling back to SDK default which AUTO-ACCEPTS shell + file changes."
            )
            return
        sync._approval_handler = self._dynamic_tool_bridge.handle_request

    async def _start_thread(
        self,
        codex: AsyncCodex,
        *,
        system_prompt: str | None,
        conversation_id: uuid.UUID,
        phase: str,
        tools: list[AgentTool] | None = None,
    ) -> tuple[Any, str | None]:
        """Start a Codex thread and return its SDK id when present."""
        phase_started_at = time.perf_counter()
        payload = thread_start_payload(
            model_id=self._model_id,
            workspace_root=str(self._workspace_root) if self._workspace_root else None,
            system_prompt=system_prompt,
            developer_instructions=CODEX_DEVELOPER_INSTRUCTIONS,
            tools=tools,
        )
        thread = await start_codex_thread(codex, payload)
        log_codex_phase(conversation_id, phase, phase_started_at)
        new_thread_id = getattr(thread, "id", None)
        return thread, new_thread_id if isinstance(new_thread_id, str) and new_thread_id else None

    async def _prepare_codex(self, conversation_id: uuid.UUID) -> AsyncCodex:
        """Return an initialized Codex client and log startup costs."""
        was_cached = self._codex is not None
        provider_started_at = time.perf_counter()
        codex = await self._ensure_codex()
        log_codex_phase(conversation_id, "ensure_client", provider_started_at, cached=was_cached)
        phase_started_at = time.perf_counter()
        await codex._ensure_initialized()
        log_codex_phase(conversation_id, "ensure_initialized", phase_started_at)
        return codex

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
        codex_thread_id: str | None = None,
        per_turn_context: str | None = None,
        images: list[dict[str, str]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Drive a Codex turn and emit native Pawrrtal StreamEvents."""
        yield {
            "type": "thinking",
            "content": "Starting Codex",
            "summary": True,
            "block_index": 0,
            "transient": True,
            "stage": "starting",
        }
        codex = await self._prepare_codex(conversation_id)
        yield {
            "type": "thinking",
            "content": "Preparing the Codex session",
            "summary": True,
            "block_index": 1,
            "transient": True,
            "stage": "preparing",
        }
        # Thread lifecycle: prefer resuming an existing Codex thread when we have one
        # persisted for this conversation. Falls back to fresh thread_start.
        # Persistence is handled by the generic turn runner when we emit a
        # provider-session creation signal.
        try:
            if codex_thread_id:
                yield {
                    "type": "thinking",
                    "content": "Resuming the Codex thread",
                    "summary": True,
                    "block_index": 2,
                    "transient": True,
                    "stage": "thread",
                }
                try:
                    phase_started_at = time.perf_counter()
                    thread = await codex.thread_resume(codex_thread_id)
                    log_codex_phase(
                        conversation_id,
                        "thread_resume",
                        phase_started_at,
                        thread_id=codex_thread_id,
                    )
                except Exception as exc:
                    if not _is_missing_codex_rollout_error(exc):
                        raise
                    logger.warning(
                        "openai_codex: persisted thread has no rollout; starting a fresh thread",
                        exc_info=True,
                    )
                    yield {
                        "type": "thinking",
                        "content": "Opening a new Codex thread",
                        "summary": True,
                        "block_index": 2,
                        "transient": True,
                        "stage": "thread",
                    }
                    thread, new_thread_id = await self._start_thread(
                        codex,
                        system_prompt=system_prompt,
                        conversation_id=conversation_id,
                        phase="thread_start_after_missing",
                        tools=tools,
                    )
                    if new_thread_id:
                        yield {
                            "type": "internal",
                            "kind": "provider_session_created",
                            "provider": "openai_codex",
                            "session_id": new_thread_id,
                        }
            else:
                yield {
                    "type": "thinking",
                    "content": "Opening a new Codex thread",
                    "summary": True,
                    "block_index": 2,
                    "transient": True,
                    "stage": "thread",
                }
                thread, new_thread_id = await self._start_thread(
                    codex,
                    system_prompt=system_prompt,
                    conversation_id=conversation_id,
                    phase="thread_start",
                    tools=tools,
                )
                # Signal to the caller that a new thread was created so it can be
                # persisted against the conversation for future resume. The
                # turn runner narrows on ``isinstance(session_id, str)`` so a
                # missing/empty id is silently dropped rather than persisted.
                if new_thread_id:
                    yield {
                        "type": "internal",
                        "kind": "provider_session_created",
                        "provider": "openai_codex",
                        "session_id": new_thread_id,
                    }
        except Exception as exc:
            logger.exception("openai_codex: thread_start/resume failed")
            yield {"type": "error", "content": f"Failed to start/resume Codex thread: {exc}"}
            return

        phase_started_at = time.perf_counter()
        run_input = _build_run_input_for_turn(
            question=question,
            history=history,
            codex_thread_id=codex_thread_id,
            per_turn_context=per_turn_context,
            images=images,
        )
        log_codex_phase(
            conversation_id,
            "build_input",
            phase_started_at,
            history_messages=0 if codex_thread_id else len(history or []),
            has_per_turn_context=bool(per_turn_context),
            images=len(images or []),
        )

        effort = _map_pawrrtal_reasoning_to_codex(reasoning_effort)

        thread_id = getattr(thread, "id", None)
        active_thread_id = thread_id if isinstance(thread_id, str) else codex_thread_id

        try:
            async for event in stream_codex_turn(
                bridge=self._dynamic_tool_bridge,
                thread=thread,
                run_input=run_input,
                effort=effort,
                summary=_get_default_reasoning_summary(),
                conversation_id=conversation_id,
                codex_thread_id=codex_thread_id,
                active_thread_id=active_thread_id,
                tools=tools,
            ):
                yield event
        except Exception as exc:
            logger.exception("openai_codex: turn streaming failed")
            yield {"type": "error", "content": f"Codex turn failed: {exc}"}
            return

        # Normal completion is signaled by the mapper emitting a "done" event
        # when it sees a TurnCompletedNotification. Nothing more to do here.


# Backwards-compat alias used in a few places during the transition.
CodexLLM = OpenAICodexProvider


def _is_missing_codex_rollout_error(exc: Exception) -> bool:
    """Return True when the SDK cannot resume an empty/precreated thread."""
    return "no rollout found for thread id" in str(exc).lower()
