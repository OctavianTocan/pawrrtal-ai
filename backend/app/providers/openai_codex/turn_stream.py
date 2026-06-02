"""Submit native Codex turns and translate streamed notifications."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from app.agents.types import AgentTool
from app.providers.base import StreamEvent
from app.providers.openai_codex.dynamic_tools import CodexDynamicToolBridge
from app.providers.openai_codex.events import map_codex_notification_to_stream_events
from app.providers.openai_codex.telemetry import log_codex_phase

_CODEX_SILENCE_HEARTBEAT_SECONDS = 5.0


async def stream_codex_turn(
    *,
    bridge: CodexDynamicToolBridge,
    thread: Any,
    run_input: Any,
    effort: Any,
    summary: Any,
    conversation_id: uuid.UUID,
    codex_thread_id: str | None,
    active_thread_id: str | None,
    tools: list[AgentTool] | None,
) -> AsyncIterator[StreamEvent]:
    """Submit one Codex turn and yield mapped Pawrrtal stream events."""
    yield {
        "type": "thinking",
        "content": "Sending the turn to Codex",
        "summary": True,
        "block_index": 3,
        "transient": True,
        "stage": "sending",
    }
    phase_started_at = time.perf_counter()
    with bridge.activate(thread_id=active_thread_id, tools=tools):
        handle = await thread.turn(run_input, effort=effort, summary=summary)
        log_codex_phase(
            conversation_id,
            "turn_submit",
            phase_started_at,
            resumed=bool(codex_thread_id),
        )
        async for event in _stream_codex_notifications(handle, conversation_id):
            yield event


async def _stream_codex_notifications(
    handle: Any,
    conversation_id: uuid.UUID,
) -> AsyncIterator[StreamEvent]:
    """Yield mapped Codex events while emitting silence heartbeats."""
    notification_stream = handle.stream().__aiter__()
    wait_started_at = time.monotonic()
    phase_started_at = time.perf_counter()
    next_notification = asyncio.create_task(notification_stream.__anext__())
    saw_event = False
    saw_delta = False
    saw_tool = False
    try:
        while True:
            done, _pending = await asyncio.wait(
                {next_notification},
                timeout=_CODEX_SILENCE_HEARTBEAT_SECONDS,
            )
            if not done:
                yield _heartbeat_event(wait_started_at)
                continue
            try:
                notification = next_notification.result()
            except StopAsyncIteration:
                break
            next_notification = asyncio.create_task(notification_stream.__anext__())
            for event in _mapped_notification_events(notification):
                saw_event, saw_delta, saw_tool = _log_firsts(
                    event=event,
                    conversation_id=conversation_id,
                    phase_started_at=phase_started_at,
                    saw_event=saw_event,
                    saw_delta=saw_delta,
                    saw_tool=saw_tool,
                )
                yield event
    finally:
        if not next_notification.done():
            next_notification.cancel()
            with suppress(asyncio.CancelledError):
                await next_notification


def _heartbeat_event(wait_started_at: float) -> StreamEvent:
    elapsed = round(time.monotonic() - wait_started_at)
    return {
        "type": "thinking",
        "content": f"Codex is still working ({elapsed}s)",
        "summary": True,
        "block_index": 4 + elapsed,
        "transient": True,
        "stage": "waiting",
    }


def _mapped_notification_events(notification: Any) -> list[StreamEvent]:
    """Return truthy mapped stream events for one Codex notification."""
    return [event for event in map_codex_notification_to_stream_events(notification) if event]


def _log_firsts(
    *,
    event: StreamEvent,
    conversation_id: uuid.UUID,
    phase_started_at: float,
    saw_event: bool,
    saw_delta: bool,
    saw_tool: bool,
) -> tuple[bool, bool, bool]:
    event_type = event.get("type")
    if not saw_event:
        log_codex_phase(
            conversation_id,
            "first_stream_event",
            phase_started_at,
            event_type=event_type,
        )
    if not saw_delta and event_type == "delta":
        log_codex_phase(conversation_id, "first_assistant_delta", phase_started_at)
        saw_delta = True
    if not saw_tool and event_type in {"tool_use", "tool_progress", "tool_result"}:
        log_codex_phase(
            conversation_id,
            "first_tool_event",
            phase_started_at,
            event_type=event_type,
        )
        saw_tool = True
    return True, saw_delta, saw_tool
