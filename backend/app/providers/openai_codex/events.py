"""Streaming event mapping for the openai_codex provider.

This module translates `Notification` objects emitted by the official Codex
Python SDK (from `turn_handle.stream()`) into Pawrrtal `StreamEvent` dicts.

The real SDK yields strongly typed Pydantic models from
`openai_codex.generated.v2_all` (and a few in `models.py`). We use `isinstance`
checks on the `.payload`, never string method name guessing.

Public entry point (used by the provider):

    from .events import map_codex_notification_to_stream_events

    for notification in turn_handle.stream():
        for event in map_codex_notification_to_stream_events(notification):
            yield event

The mapper is intentionally defensive: unknown or unexpected notification
shapes must never raise. They are logged at debug level and ignored.
"""

from __future__ import annotations

import base64
import binascii
import logging
from collections.abc import Iterator
from typing import Any

from app.providers.base import StreamEvent

# Use the vendored/installed SDK bootstrap. We resolve the specific generated
# notification classes lazily inside the mapper (avoids circular import during
# package init, since __init__.py imports provider which imports us).
from ._vendor import get_openai_codex_module
from .tool_events import (
    plan_text,
    tool_result_for_item,
    tool_use_for_item,
    truncate_tool_output,
)

_openai_codex_mod = None


def _get_sdk_type(name: str) -> Any:
    # ``_openai_codex_mod`` caches the resolved SDK module on first hit so we
    # don't re-run the (sys.path-mutating) bootstrap on every notification.
    # A module-scope cache is the simplest correct fit; refactoring to a
    # callable singleton would not change behaviour.
    global _openai_codex_mod  # noqa: PLW0603
    if _openai_codex_mod is None:
        _openai_codex_mod = get_openai_codex_module()
    # Try top level first, then generated.v2_all (current vendored layout)
    val = getattr(_openai_codex_mod, name, None)
    if val is not None:
        return val
    v2 = getattr(getattr(_openai_codex_mod, "generated", None), "v2_all", None)
    return getattr(v2, name, None) if v2 is not None else None


logger = logging.getLogger(__name__)


# Cached resolved types (populated on first use of the mapper)
_sdk_types: dict[str, Any] = {}


def _sdk(name: str) -> Any:
    """Lazily resolve a notification / model type from the SDK (with vendored layout support)."""
    if name not in _sdk_types:
        _sdk_types[name] = _get_sdk_type(name)
    return _sdk_types[name]


def _handle_item_completed(item: Any) -> Iterator[StreamEvent]:
    """Translate an ItemCompletedNotification's inner item into stream events.

    Split out of ``map_codex_notification_to_stream_events`` so the parent
    mapper stays under sentrux's max cyclomatic complexity budget (30).
    Image generation is the only branch that currently emits an event;
    other item kinds (command results, file changes, tool call results)
    have already had their incremental content carried by the deltas.
    """
    inner = getattr(item, "root", item)

    if getattr(inner, "type", None) == "image_generation" or "ImageGeneration" in str(type(inner)):
        yield {
            "type": "artifact",
            "kind": "image",
            "data": getattr(inner, "result", None) or inner,
            "provider": "openai_codex",
        }
        return

    tool_result = tool_result_for_item(inner)
    if tool_result is not None:
        yield tool_result


def _map_turn_lifecycle(payload: Any) -> list[StreamEvent] | None:
    """Map turn-start, plan, diff, and item-start notifications."""
    TurnStartedT = _sdk("TurnStartedNotification")  # noqa: N806
    if TurnStartedT and isinstance(payload, TurnStartedT):
        return [
            {
                "type": "thinking",
                "content": "Codex started the turn",
                "summary": True,
                "block_index": 0,
                "transient": True,
                "stage": "started",
            }
        ]

    TurnPlanUpdatedT = _sdk("TurnPlanUpdatedNotification")  # noqa: N806
    if TurnPlanUpdatedT and isinstance(payload, TurnPlanUpdatedT):
        plan = plan_text(
            getattr(payload, "plan", None),
            getattr(payload, "explanation", None),
        )
        return (
            [
                {
                    "type": "thinking",
                    "content": plan,
                    "summary": True,
                    "block_index": 1,
                }
            ]
            if plan
            else []
        )

    TurnDiffUpdatedT = _sdk("TurnDiffUpdatedNotification")  # noqa: N806
    if TurnDiffUpdatedT and isinstance(payload, TurnDiffUpdatedT):
        diff = getattr(payload, "diff", None)
        return (
            [
                {
                    "type": "thinking",
                    "content": "Codex prepared file changes.",
                    "summary": True,
                    "block_index": 1,
                }
            ]
            if diff
            else []
        )

    PlanDeltaT = _sdk("PlanDeltaNotification")  # noqa: N806
    if PlanDeltaT and isinstance(payload, PlanDeltaT):
        delta = getattr(payload, "delta", None)
        return (
            [
                {
                    "type": "thinking",
                    "content": str(delta),
                    "summary": True,
                    "block_index": 1,
                }
            ]
            if delta
            else []
        )

    ItemStartedT = _sdk("ItemStartedNotification")  # noqa: N806
    if ItemStartedT and isinstance(payload, ItemStartedT):
        event = tool_use_for_item(payload.item)
        return [event] if event is not None else []

    return None


def _map_text_and_reasoning(payload: Any) -> list[StreamEvent] | None:
    """Map normal assistant output plus reasoning/thinking deltas."""
    AgentMessageDeltaT = _sdk("AgentMessageDeltaNotification")  # noqa: N806
    if AgentMessageDeltaT and isinstance(payload, AgentMessageDeltaT):
        return [{"type": "delta", "content": payload.delta}] if payload.delta else []

    ReasoningSummaryT = _sdk("ReasoningSummaryTextDeltaNotification")  # noqa: N806
    if ReasoningSummaryT and isinstance(payload, ReasoningSummaryT):
        return (
            [
                {
                    "type": "thinking",
                    "content": payload.delta,
                    "summary": True,
                    "block_index": 2,
                }
            ]
            if payload.delta
            else []
        )

    ReasoningTextT = _sdk("ReasoningTextDeltaNotification")  # noqa: N806
    if ReasoningTextT and isinstance(payload, ReasoningTextT):
        return (
            [
                {
                    "type": "thinking",
                    "content": payload.delta,
                    "summary": False,
                    "block_index": 3,
                }
            ]
            if payload.delta
            else []
        )

    return None


def _map_tool_progress(payload: Any) -> list[StreamEvent] | None:
    """Map tool-progress notifications emitted while Codex works."""
    CommandOutputT = _sdk("CommandExecutionOutputDeltaNotification")  # noqa: N806
    if CommandOutputT and isinstance(payload, CommandOutputT):
        return (
            [
                {
                    "type": "tool_progress",
                    "tool_use_id": payload.item_id,
                    "content": truncate_tool_output(payload.delta),
                }
            ]
            if payload.delta
            else []
        )

    CommandExecOutputT = _sdk("CommandExecOutputDeltaNotification")  # noqa: N806
    if CommandExecOutputT and isinstance(payload, CommandExecOutputT):
        process_id = str(getattr(payload, "process_id", "") or "command")
        delta = _decode_command_exec_delta(payload)
        return [_command_exec_progress_event(payload, process_id, delta)] if delta else []

    FileChangeOutputT = _sdk("FileChangeOutputDeltaNotification")  # noqa: N806
    if FileChangeOutputT and isinstance(payload, FileChangeOutputT):
        return (
            [
                {
                    "type": "tool_progress",
                    "tool_use_id": payload.item_id,
                    "content": truncate_tool_output(payload.delta),
                }
            ]
            if payload.delta
            else []
        )

    McpProgressT = _sdk("McpToolCallProgressNotification")  # noqa: N806
    if McpProgressT and isinstance(payload, McpProgressT):
        return [
            {
                "type": "tool_progress",
                "tool_use_id": payload.item_id,
                "content": truncate_tool_output(str(payload.message)),
            }
        ]

    return None


def _command_exec_progress_event(payload: Any, process_id: str, delta: str) -> StreamEvent:
    """Build a progress event from a legacy command-exec delta payload."""
    stream = str(getattr(payload, "stream", "") or "").strip()
    cap_reached = bool(getattr(payload, "cap_reached", False))
    prefix = f"{stream}: " if stream else ""
    suffix = "\n... output cap reached" if cap_reached else ""
    return {
        "type": "tool_progress",
        "tool_use_id": process_id,
        "content": truncate_tool_output(f"{prefix}{delta}{suffix}"),
    }


def _map_completion_status(payload: Any) -> list[StreamEvent] | None:
    """Map turn completion, item completion, warnings, and reroutes."""
    TurnCompletedT = _sdk("TurnCompletedNotification")  # noqa: N806
    if TurnCompletedT and isinstance(payload, TurnCompletedT):
        turn = payload.turn
        events: list[StreamEvent] = []
        if turn.status == "failed" and turn.error:
            msg = turn.error.message or str(turn.error)
            events.append({"type": "error", "content": f"Codex turn failed: {msg}"})
        events.append({"type": "done"})
        return events

    ItemCompletedT = _sdk("ItemCompletedNotification")  # noqa: N806
    if ItemCompletedT and isinstance(payload, ItemCompletedT):
        return list(_handle_item_completed(payload.item))

    WarningT = _sdk("WarningNotification")  # noqa: N806
    if WarningT and isinstance(payload, WarningT):
        message = getattr(payload, "message", None)
        return [_warning_event(str(message))] if message else []

    ConfigWarningT = _sdk("ConfigWarningNotification")  # noqa: N806
    if ConfigWarningT and isinstance(payload, ConfigWarningT):
        message = getattr(payload, "message", None)
        return [_warning_event(str(message))] if message else []

    ModelReroutedT = _sdk("ModelReroutedNotification")  # noqa: N806
    if ModelReroutedT and isinstance(payload, ModelReroutedT):
        return [_warning_event("Codex rerouted the model for this turn.")]

    return None


def _warning_event(message: str) -> StreamEvent:
    """Create a summary thinking event for warning-like Codex notifications."""
    return {"type": "thinking", "content": message, "summary": True, "block_index": 4}


def _map_accounting_and_errors(payload: Any) -> list[StreamEvent] | None:
    """Map usage, explicit errors, and unknown notifications."""
    UsageT = _sdk("ThreadTokenUsageUpdatedNotification")  # noqa: N806
    if UsageT and isinstance(payload, UsageT):
        usage = payload.token_usage
        last = getattr(usage, "last", None)
        total = getattr(usage, "total", None)
        if last is None:
            return []
        event: StreamEvent = {
            "type": "usage",
            "input_tokens": getattr(last, "input_tokens", 0) or 0,
            "output_tokens": getattr(last, "output_tokens", 0) or 0,
        }
        if total is not None:
            event["total_input_tokens"] = getattr(total, "input_tokens", 0) or 0
            event["total_output_tokens"] = getattr(total, "output_tokens", 0) or 0
        return [event]

    ErrorT = _sdk("ErrorNotification")  # noqa: N806
    if ErrorT and isinstance(payload, ErrorT):
        err = payload.error
        msg = getattr(err, "message", None) or str(err)
        return [{"type": "error", "content": f"Codex error: {msg}"}]

    UnknownT = _sdk("UnknownNotification")  # noqa: N806
    if UnknownT and isinstance(payload, UnknownT):
        logger.debug("openai_codex.events: UnknownNotification params=%s", payload.params)
        return []

    return None


def _mapped_payload_events(payload: Any) -> list[StreamEvent] | None:
    """Dispatch a Codex payload to the first matching focused mapper."""
    for mapper in (
        _map_turn_lifecycle,
        _map_text_and_reasoning,
        _map_tool_progress,
        _map_completion_status,
        _map_accounting_and_errors,
    ):
        events = mapper(payload)
        if events is not None:
            return events
    return None


def map_codex_notification_to_stream_events(notification: Any) -> Iterator[StreamEvent]:
    """Convert one Codex SDK Notification into zero or more Pawrrtal StreamEvents.

    This is the critical translation layer that makes Codex feel native
    (deltas, thinking blocks, tool calls, artifacts, usage, completion, errors).

    Local variables that hold SDK type *classes* use PascalCase
    (``NotificationT``) because they are types resolved at runtime; ``# noqa:
    N806`` is applied on that line. Renaming it to ``snake_case`` would lie
    about its kind.
    """
    NotificationT = _sdk("Notification")  # noqa: N806
    if NotificationT and not isinstance(notification, NotificationT):
        logger.debug("openai_codex.events: received non-Notification %r", type(notification))
        return

    payload = getattr(notification, "payload", notification)
    events = _mapped_payload_events(payload)
    if events is not None:
        yield from events
        return

    logger.debug(
        "openai_codex.events: unhandled notification payload type=%s method=%s",
        type(payload).__name__,
        getattr(notification, "method", None),
    )


def _decode_command_exec_delta(payload: Any) -> str:
    """Decode legacy command-exec base64 deltas from the Codex SDK."""
    raw = getattr(payload, "delta_base64", None)
    if not raw:
        return ""
    try:
        decoded = base64.b64decode(str(raw), validate=True)
    except (binascii.Error, ValueError):
        return ""
    return decoded.decode("utf-8", errors="replace")
