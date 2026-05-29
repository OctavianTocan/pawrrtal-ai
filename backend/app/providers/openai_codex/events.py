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

import logging
from collections.abc import Iterator
from typing import Any

from app.providers.base import StreamEvent

# Use the vendored/installed SDK bootstrap. We resolve the specific generated
# notification classes lazily inside the mapper (avoids circular import during
# package init, since __init__.py imports provider which imports us).
from ._vendor import get_openai_codex_module

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


def map_codex_notification_to_stream_events(  # noqa: C901, PLR0911, PLR0912
    notification: Any,
) -> Iterator[StreamEvent]:
    """Convert one Codex SDK Notification into zero or more Pawrrtal StreamEvents.

    This is the critical translation layer that makes Codex feel native
    (deltas, thinking blocks, tool calls, artifacts, usage, completion, errors).

    Ruff's ``C901`` / ``PLR0911`` / ``PLR0912`` (cyclomatic + return-count +
    branch-count) are suppressed at the function level: the dispatch is a
    flat ``isinstance`` chain — one branch per SDK notification class —
    where every branch is intentionally a top-level ``if … return`` so the
    mapper stays grep-friendly per notification kind. Splitting it into
    helpers would obscure the 1:1 SDK-type → StreamEvent mapping, which is
    the core value of this module.

    Local variables that hold SDK type *classes* use PascalCase (``NotificationT``,
    ``AgentMessageDeltaT``, …) because they are types resolved at runtime;
    ``# noqa: N806`` is applied per-line on those lines. Renaming them to
    ``snake_case`` would lie about their kind.
    """
    NotificationT = _sdk("Notification")  # noqa: N806
    if NotificationT and not isinstance(notification, NotificationT):
        logger.debug("openai_codex.events: received non-Notification %r", type(notification))
        return

    payload = getattr(notification, "payload", notification)

    # ------------------------------------------------------------------
    # Text output (normal assistant message deltas)
    # ------------------------------------------------------------------
    AgentMessageDeltaT = _sdk("AgentMessageDeltaNotification")  # noqa: N806
    if AgentMessageDeltaT and isinstance(payload, AgentMessageDeltaT):
        if payload.delta:
            yield {"type": "delta", "content": payload.delta}
        return

    # ------------------------------------------------------------------
    # Reasoning / thinking (summary + raw)
    # ------------------------------------------------------------------
    ReasoningSummaryT = _sdk("ReasoningSummaryTextDeltaNotification")  # noqa: N806
    if ReasoningSummaryT and isinstance(payload, ReasoningSummaryT):
        if payload.delta:
            yield {
                "type": "thinking",
                "content": payload.delta,
                "summary": True,
            }
        return

    ReasoningTextT = _sdk("ReasoningTextDeltaNotification")  # noqa: N806
    if ReasoningTextT and isinstance(payload, ReasoningTextT):
        if payload.delta:
            yield {
                "type": "thinking",
                "content": payload.delta,
                "summary": False,
            }
        return

    # ------------------------------------------------------------------
    # Turn / item lifecycle completion (most important terminal signal)
    # ------------------------------------------------------------------
    TurnCompletedT = _sdk("TurnCompletedNotification")  # noqa: N806
    if TurnCompletedT and isinstance(payload, TurnCompletedT):
        turn = payload.turn
        if turn.status == "failed" and turn.error:
            msg = turn.error.message or str(turn.error)
            yield {"type": "error", "content": f"Codex turn failed: {msg}"}
        yield {"type": "done"}
        return

    # Item completion can carry final artifacts (images, etc.) or tool results.
    # The inner-branch logic lives in ``_handle_item_completed`` so this
    # dispatcher stays under sentrux's cyclomatic budget; the helper keeps the
    # 1:1 SDK-type → StreamEvent mapping that makes this file grep-friendly.
    ItemCompletedT = _sdk("ItemCompletedNotification")  # noqa: N806
    if ItemCompletedT and isinstance(payload, ItemCompletedT):
        yield from _handle_item_completed(payload.item)
        return

    # ------------------------------------------------------------------
    # Usage / cost accounting
    # ------------------------------------------------------------------
    UsageT = _sdk("ThreadTokenUsageUpdatedNotification")  # noqa: N806
    if UsageT and isinstance(payload, UsageT):
        usage = payload.token_usage
        # ThreadTokenUsage has .total and .last (TokenUsageBreakdown)
        total = getattr(usage, "total", None)
        if total:
            yield {
                "type": "usage",
                "input_tokens": getattr(total, "input_tokens", 0) or 0,
                "output_tokens": getattr(total, "output_tokens", 0) or 0,
                # cost_usd will be computed by the cost tracker from model + tokens
            }
        return

    # ------------------------------------------------------------------
    # Explicit errors
    # ------------------------------------------------------------------
    ErrorT = _sdk("ErrorNotification")  # noqa: N806
    if ErrorT and isinstance(payload, ErrorT):
        err = payload.error
        msg = getattr(err, "message", None) or str(err)
        yield {"type": "error", "content": f"Codex error: {msg}"}
        return

    # ------------------------------------------------------------------
    # Unknown / not-yet-mapped notifications (defensive no-op)
    # ------------------------------------------------------------------
    UnknownT = _sdk("UnknownNotification")  # noqa: N806
    if UnknownT and isinstance(payload, UnknownT):
        logger.debug("openai_codex.events: UnknownNotification params=%s", payload.params)
        return

    # Any other payload we haven't mapped yet — log once for debugging
    # during rollout, but never crash the stream.
    logger.debug(
        "openai_codex.events: unhandled notification payload type=%s method=%s",
        type(payload).__name__,
        getattr(notification, "method", None),
    )
