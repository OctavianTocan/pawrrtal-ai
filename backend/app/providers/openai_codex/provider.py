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

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any

from app.agents.types import AgentTool
from app.providers.base import (
    ReasoningEffort as PawReasoningEffort,
)
from app.providers.base import (
    StreamEvent,
)
from app.providers.openai_codex.auth import build_app_server_config
from app.providers.openai_codex.events import (
    map_codex_notification_to_stream_events,
)
from app.providers.openai_codex.inputs import build_codex_run_input
from app.providers.openai_codex.prompting import CODEX_DEVELOPER_INSTRUCTIONS

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
from openai_codex import ApprovalMode, AppServerConfig, AsyncCodex, TextInput
from openai_codex.generated.v2_all import ReasoningEffort as CodexReasoningEffort
from openai_codex.generated.v2_all import SandboxMode

logger = logging.getLogger(__name__)

_CODEX_SILENCE_HEARTBEAT_SECONDS = 5.0

_DENY_ALL_DECISION: dict[str, str] = {"decision": "deny"}


def _deny_all_approval_handler(method: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """Reject every escalation request.

    The SDK's default (vendor/codex/sdk/python/src/openai_codex/client.py:597)
    accepts shell exec and file writes. Pawrrtal turns must not let the
    spawned codex app-server modify the workspace silently. Per-tool
    approvals are handled by the chat router's tool composition (see
    .claude/rules/architecture/no-tools-in-providers.md). Once the tool
    bridge lands (bean pawrrtal-roi0), this handler should be replaced
    with one that consults the agent loop.
    """
    if method in (
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
    ):
        return _DENY_ALL_DECISION
    return {}


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

    @property
    def model_id(self) -> str:
        """Native Codex model id used when creating or resuming SDK threads."""
        return self._model_id

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
        sync._approval_handler = _deny_all_approval_handler

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
        if tools:
            logger.debug(
                "openai_codex provider: tools provided but not yet wired for model=%s "
                "(text-only path for v1)",
                self._model_id,
            )

        yield {
            "type": "thinking",
            "content": "Starting Codex",
            "summary": True,
            "block_index": 0,
            "transient": True,
            "stage": "starting",
        }
        codex = await self._ensure_codex()
        yield {
            "type": "thinking",
            "content": "Preparing the Codex session",
            "summary": True,
            "block_index": 1,
            "transient": True,
            "stage": "preparing",
        }
        await codex._ensure_initialized()  # ensure the app-server is up

        # Thread lifecycle: prefer resuming an existing Codex thread when we have one
        # persisted for this conversation. Falls back to fresh thread_start.
        # The actual persistence (storing codex_thread_id on the Conversation row)
        # is handled by the turn runner / caller when we emit a thread creation signal.
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
                    thread = await codex.thread_resume(codex_thread_id)
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
                    thread = await codex.thread_start(
                        model=self._model_id,
                        cwd=str(self._workspace_root) if self._workspace_root else None,
                        base_instructions=system_prompt,
                        developer_instructions=CODEX_DEVELOPER_INSTRUCTIONS,
                        approval_mode=ApprovalMode.deny_all,
                        sandbox=SandboxMode.read_only,
                    )
                    new_thread_id = getattr(thread, "id", None)
                    if isinstance(new_thread_id, str) and new_thread_id:
                        yield {
                            "type": "internal",
                            "kind": "codex_thread_created",
                            "thread_id": new_thread_id,
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
                thread = await codex.thread_start(
                    model=self._model_id,
                    cwd=str(self._workspace_root) if self._workspace_root else None,
                    base_instructions=system_prompt,
                    developer_instructions=CODEX_DEVELOPER_INSTRUCTIONS,
                    approval_mode=ApprovalMode.deny_all,
                    sandbox=SandboxMode.read_only,
                )
                # Signal to the caller that a new thread was created so it can be
                # persisted against the conversation for future resume. The
                # turn runner narrows on ``isinstance(thread_id, str)`` so a
                # missing/empty id is silently dropped rather than persisted.
                new_thread_id = getattr(thread, "id", None)
                if isinstance(new_thread_id, str) and new_thread_id:
                    yield {
                        "type": "internal",
                        "kind": "codex_thread_created",
                        "thread_id": new_thread_id,
                    }
        except Exception as exc:
            logger.exception("openai_codex: thread_start/resume failed")
            yield {"type": "error", "content": f"Failed to start/resume Codex thread: {exc}"}
            return

        # Build rich input using the dedicated translation layer.
        # This gives us proper history replay, previous thinking, tool results,
        # and attached images — the main missing piece from the v1 implementation.
        try:
            run_input = build_codex_run_input(
                question=question,
                history=[] if codex_thread_id else history,
                per_turn_context=per_turn_context,
                images=images,
            )
        except Exception:
            # Fallback for any SDK input shape changes or translation issues
            run_input = TextInput(text=question) if question else question

        effort = _map_pawrrtal_reasoning_to_codex(reasoning_effort)

        try:
            yield {
                "type": "thinking",
                "content": "Sending the turn to Codex",
                "summary": True,
                "block_index": 3,
                "transient": True,
                "stage": "sending",
            }
            handle = await thread.turn(
                run_input,
                effort=effort,
                summary=_get_default_reasoning_summary(),
            )

            # The high-level async handle exposes a stream of Notification objects.
            # We consume it directly.
            async for event in _stream_codex_notifications(handle):
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


async def _stream_codex_notifications(handle: Any) -> AsyncIterator[StreamEvent]:
    """Yield mapped Codex events while emitting silence heartbeats."""
    notification_stream = handle.stream().__aiter__()
    wait_started_at = time.monotonic()
    next_notification = asyncio.create_task(notification_stream.__anext__())
    try:
        while True:
            done, _pending = await asyncio.wait(
                {next_notification},
                timeout=_CODEX_SILENCE_HEARTBEAT_SECONDS,
            )
            if not done:
                elapsed = round(time.monotonic() - wait_started_at)
                yield {
                    "type": "thinking",
                    "content": f"Codex is still working ({elapsed}s)",
                    "summary": True,
                    "block_index": 4 + elapsed,
                    "transient": True,
                    "stage": "waiting",
                }
                continue
            try:
                notification = next_notification.result()
            except StopAsyncIteration:
                break
            next_notification = asyncio.create_task(notification_stream.__anext__())
            for event in _mapped_notification_events(notification):
                yield event
    finally:
        if not next_notification.done():
            next_notification.cancel()
            with suppress(asyncio.CancelledError):
                await next_notification


def _mapped_notification_events(notification: Any) -> list[StreamEvent]:
    """Return truthy mapped stream events for one Codex notification."""
    return [event for event in map_codex_notification_to_stream_events(notification) if event]
