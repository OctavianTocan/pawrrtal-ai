"""Background runner for one subagent invocation.

Lifecycle:

  1. The spawn tool (PR 4) creates the ``subagents`` row at
     ``status="running"`` and calls :func:`start_subagent`.
  2. :func:`start_subagent` creates an :class:`asyncio.Task` that runs
     :func:`_run_subagent`, registers it in the in-process registry
     (strong-ref + auto-cleanup ``done_callback``), and returns.
  3. The task runs to completion off the HTTP request thread.  When
     done it:
       * UPDATEs the row to a terminal status with result / error /
         cost / token counts.
       * Writes a ``cost_ledger`` row keyed to the parent's
         conversation_id with ``surface="subagent"`` so the daily cap
         counts it naturally.
       * Publishes :class:`~app.core.subagents.events.SubagentCompletedEvent`
         on the event bus.  PR 4's ``wait_for_subagents`` tool
         subscribes to unblock the parent.

The runner is provider-neutral and tool-neutral: it accepts a fully
resolved :class:`Persona` (the spawn tool resolves overrides) and a
pre-filtered ``list[AgentTool]`` (the spawn tool enforces the
``tools_allow`` cap).  This file's only knowledge of the persona system
is that it has a model name and a system prompt.

Per :doc:`.claude/rules/architecture/no-tools-in-providers`: this
module composes per-spawn (not in a provider).  Tool factories are
imported only here, not in any ``app.core.providers.*`` file.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.api._chat_permissions import build_chat_permission_check
from app.core.chat_aggregator import ChatTurnAggregator
from app.core.config import settings
from app.core.event_bus import publish_if_available
from app.core.governance.cost_tracker import PostgresCostLedger, record_turn_cost
from app.core.providers.base import AILLM, StreamEvent
from app.core.providers.factory import resolve_llm
from app.core.providers.model_id import parse_model_id
from app.core.subagents.events import SubagentCompletedEvent
from app.core.subagents.persona import Persona
from app.core.subagents.registry import register as register_task
from app.crud.subagent import finalize_subagent
from app.db import async_session_maker

logger = logging.getLogger(__name__)


# Surface label used on the cost-ledger row and on log lines so audit
# queries can distinguish subagent spend from interactive chat spend.
SUBAGENT_COST_SURFACE: str = "subagent"


async def start_subagent(
    *,
    subagent_id: uuid.UUID,
    handle: str,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    workspace_root: Path,
    surface: str,
    persona: Persona,
    task: str,
    child_tools: list,
    session_maker=None,
) -> asyncio.Task[None]:
    """Schedule the background runner and return its ``asyncio.Task``.

    Test seam: the returned task can be ``await``ed by tests to drive
    a deterministic full lifecycle.  Production callers fire-and-forget
    — the registry holds the strong ref and the ``done_callback``
    drops it on completion.

    ``child_tools`` is typed ``list`` (not ``list[AgentTool]``) here
    because the explicit annotation would force an
    ``app.core.agent_loop`` import that conflicts with the layering
    sentrux gate; tools are still ``AgentTool`` instances at runtime.
    """
    coroutine = _run_subagent(
        subagent_id=subagent_id,
        handle=handle,
        conversation_id=conversation_id,
        user_id=user_id,
        workspace_root=workspace_root,
        surface=surface,
        persona=persona,
        task=task,
        child_tools=child_tools,
        session_maker=session_maker or async_session_maker,
    )
    task = asyncio.create_task(coroutine, name=f"subagent:{handle}")
    register_task(handle, task)
    return task


async def _run_subagent(
    *,
    subagent_id: uuid.UUID,
    handle: str,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    workspace_root: Path,
    surface: str,
    persona: Persona,
    task: str,
    child_tools: list,
    session_maker,
) -> None:
    """Run the child :class:`AILLM` turn and finalize the durable row.

    Wraps everything in a single ``try / except / finally`` so any exit
    path — success, cancellation, timeout, provider error — produces
    exactly one terminal-status UPDATE, one cost-ledger row, and one
    :class:`SubagentCompletedEvent`.  Anything else risks the
    in-process registry diverging from the DB state.

    Permission gate: per option (b), rebuilt from scratch at spawn
    time via :func:`build_chat_permission_check` so the policy reflects
    the workspace's current ``enabled_tools`` rather than a stale
    snapshot from the parent's HTTP request closure.
    """
    started_at = time.monotonic()
    aggregator = ChatTurnAggregator()
    status, result, error = "failed", None, "runner did not record an outcome"

    try:
        provider = resolve_llm(persona.model, user_id=user_id)
        permission_check = build_chat_permission_check(
            user_id=user_id,
            workspace_root=workspace_root,
            conversation_id=conversation_id,
            surface=surface,
        )
        result_text = await asyncio.wait_for(
            _drain_provider_stream(
                provider=provider,
                task=task,
                conversation_id=conversation_id,
                user_id=user_id,
                child_tools=child_tools,
                system_prompt=persona.system_prompt,
                permission_check=permission_check,
                aggregator=aggregator,
            ),
            timeout=persona.max_wall_clock_seconds,
        )
        status, result, error = "succeeded", result_text, None
    except asyncio.CancelledError:
        status, result, error = "cancelled", None, "cancelled by parent"
        raise
    except TimeoutError:
        status, result, error = (
            "failed",
            None,
            f"exceeded persona max_wall_clock_seconds={persona.max_wall_clock_seconds:.0f}",
        )
    except Exception as exc:
        # Broad catch is intentional here: the runner is the last line
        # of defence — any unhandled exception inside provider.stream
        # would otherwise crash the background task and leave the
        # durable row stuck at "running" forever.  The startup reaper
        # would eventually catch it but we have a fresher record.
        logger.exception("SUBAGENT_RUN_ERR handle=%s subagent_id=%s", handle, subagent_id)
        status, result, error = "failed", None, f"runner error: {exc}"
    finally:
        duration_seconds = time.monotonic() - started_at
        await _persist_terminal_state(
            session_maker=session_maker,
            subagent_id=subagent_id,
            handle=handle,
            conversation_id=conversation_id,
            user_id=user_id,
            persona=persona,
            aggregator=aggregator,
            status=status,
            result=result,
            error=error,
            duration_seconds=duration_seconds,
        )


async def _drain_provider_stream(
    *,
    provider: AILLM,
    task: str,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    child_tools: list,
    system_prompt: str,
    permission_check,
    aggregator: ChatTurnAggregator,
) -> str:
    """Iterate the child's ``provider.stream(...)`` and return final text.

    Drains every event into the per-child aggregator (so cost +
    tokens land on the ledger when finalised) and collects ``delta``
    events into the result string.  Returns the concatenated
    assistant text, or an empty string when the child produced no
    user-facing output.
    """
    text_parts: list[str] = []
    async for event in provider.stream(
        task,
        conversation_id,
        user_id,
        history=[],  # fresh transcript — child has no memory of parent conversation.
        tools=child_tools,
        system_prompt=system_prompt,
        permission_check=permission_check,
    ):
        aggregator.apply(event)
        _collect_text_delta(event, text_parts)
    return "".join(text_parts).strip()


def _collect_text_delta(event: StreamEvent, text_parts: list[str]) -> None:
    """Accumulate user-facing text from a ``delta`` event.

    Tiny helper extracted so the drain loop stays inside the project's
    nesting budget (``scripts/check-nesting.py``).
    """
    if event.get("type") == "delta":
        chunk = event.get("content")
        if isinstance(chunk, str):
            text_parts.append(chunk)


async def _persist_terminal_state(
    *,
    session_maker,
    subagent_id: uuid.UUID,
    handle: str,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    persona: Persona,
    aggregator: ChatTurnAggregator,
    status: str,
    result: str | None,
    error: str | None,
    duration_seconds: float,
) -> None:
    """Finalize the durable row, write the cost-ledger row, publish completion.

    Opens a fresh ``async_session_maker`` session because the spawn's
    HTTP request session has long since closed by the time the
    background task reaches a terminal state.

    Failures here are logged but never re-raised — the background task
    is exiting anyway and we don't want to mask the original error (if
    any) by raising a persistence problem on top of it.  The startup
    reaper picks up rows whose durable terminal state never landed.
    """
    completed_at = datetime.now(UTC).replace(tzinfo=None)
    try:
        async with session_maker() as session:
            patched = await finalize_subagent(
                session,
                subagent_id=subagent_id,
                status=status,  # type: ignore[arg-type]
                completed_at=completed_at,
                result=result,
                error=error,
                cost_usd=aggregator.total_cost_usd,
                input_tokens=aggregator.total_input_tokens,
                output_tokens=aggregator.total_output_tokens,
            )
            if patched and settings.cost_tracker_enabled:
                await _record_cost_ledger_row(
                    session=session,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    model_id=persona.model,
                    aggregator=aggregator,
                )
            await session.commit()
    except Exception:
        logger.exception(
            "SUBAGENT_FINALIZE_ERR handle=%s subagent_id=%s status=%s",
            handle,
            subagent_id,
            status,
        )

    await publish_if_available(
        SubagentCompletedEvent(
            subagent_id=subagent_id,
            handle=handle,
            conversation_id=conversation_id,
            user_id=user_id,
            persona_name=persona.name,
            status=status,
            result=result,
            error=error,
            cost_usd=aggregator.total_cost_usd,
            duration_seconds=duration_seconds,
        )
    )


async def _record_cost_ledger_row(
    *,
    session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    model_id: str,
    aggregator: ChatTurnAggregator,
) -> None:
    """Write the subagent's spend to ``cost_ledger`` with surface marker.

    Daily cap reads the same ledger, so subagent spend counts toward
    the per-user budget naturally.  ``surface="subagent"`` lets audit
    queries partition chat vs subagent spend without a JOIN.
    """
    try:
        provider_slug = parse_model_id(model_id).host.value
    except Exception:
        provider_slug = "unknown"
    ledger = PostgresCostLedger(session=session)
    try:
        await record_turn_cost(
            ledger,
            user_id=user_id,
            conversation_id=conversation_id,
            provider=provider_slug,
            model_id=model_id,
            input_tokens=aggregator.total_input_tokens,
            output_tokens=aggregator.total_output_tokens,
            cost_usd=aggregator.total_cost_usd,
            surface=SUBAGENT_COST_SURFACE,
        )
    except Exception:
        logger.exception(
            "SUBAGENT_COST_LEDGER_ERR conversation_id=%s model_id=%s",
            conversation_id,
            model_id,
        )


__all__ = ["SUBAGENT_COST_SURFACE", "start_subagent"]
