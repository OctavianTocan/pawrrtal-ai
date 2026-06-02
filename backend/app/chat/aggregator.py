"""Aggregate provider stream events into the rich shape the chat UI persists.

@fileoverview Mirrors the frontend reducer in
``frontend/features/chat/chat-reducer.ts`` so a stream produces identical
state on the client (live) and on the server (persisted). One instance of
:class:`ChatTurnAggregator` lives for the duration of a single assistant
turn; the chat endpoint feeds it every :class:`StreamEvent` and writes the
final snapshot into the ``chat_messages`` row when the stream ends.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.governance.secret_redaction import redact_mapping
from app.infrastructure.config import settings
from app.providers.base import StreamEvent


def _maybe_redact(payload: Any) -> Any:
    """Run the redaction pass only when the global toggle is on.

    Centralised so the aggregator body stays readable. The toggle is
    checked at call time (not at import time) so tests can flip it
    via the settings singleton without re-importing the module.
    """
    if not settings.secret_redaction_enabled:
        return payload
    return redact_mapping(payload)


@dataclass
class _ToolCall:
    id: str
    name: str
    input: dict[str, Any]
    display: dict[str, Any] | None = None
    status: str = "pending"
    result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the JSON shape persisted in the chat_messages row."""
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "input": self.input,
            "status": self.status,
        }
        if self.display is not None:
            payload["display"] = self.display
        if self.result is not None:
            payload["result"] = self.result
        return payload


# Verbose levels (PR 07).  Filter applied to events before the
# aggregator persists them and before the Telegram channel renders
# inline tool glyphs.  Mirrors CCT's ``/verbose 0|1|2`` semantics.
VERBOSE_QUIET = 0
VERBOSE_NORMAL = 1
VERBOSE_DETAILED = 2


def should_emit_event(event: StreamEvent, verbose_level: int) -> bool:
    """Return ``True`` when the event survives the configured verbose filter.

    Level semantics (matches CCT):
    * ``0`` (quiet) — only ``delta`` (final answer) + ``error`` + ``usage``
      survive.  Tool calls and thinking are dropped.
    * ``1`` (normal, default) — adds ``tool_use`` + ``tool_progress`` +
      ``tool_result`` + ``artifact`` + ``message`` plus safe thinking
      summaries so the user sees what the agent is doing inline. Raw
      thinking remains suppressed.
    * ``2`` (detailed) — adds ``thinking`` so chain-of-thought is
      visible.  Everything passes through.
    """
    event_type = event.get("type")
    if verbose_level >= VERBOSE_DETAILED:
        return True
    if event_type == "thinking" and not event.get("summary"):
        return False
    if verbose_level >= VERBOSE_NORMAL:
        return True
    # Quiet: only deltas + errors + usage.
    return event_type in {"delta", "error", "usage"}


@dataclass
class ChatTurnAggregator:
    """Fold provider stream events into the persisted assistant-turn shape.

    The aggregator is intentionally state-machine-light: it just appends to a
    few lists/strings. All semantics (e.g. which timeline entries merge) match
    the frontend reducer so live and rehydrated views are byte-identical.

    PR 04: ``total_input_tokens`` / ``total_output_tokens`` /
    ``total_cost_usd`` are folded from ``usage`` events emitted by the
    provider on the terminal turn.  The chat router reads these after
    the stream completes and writes a ``cost_ledger`` row.  Multiple
    ``usage`` events sum (some providers emit per-turn, others per-call).
    """

    content: str = ""
    thinking: str = ""
    started_at_monotonic: float | None = None
    error_text: str | None = None
    tool_calls: list[_ToolCall] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    def _mark_started(self) -> None:
        if self.started_at_monotonic is None:
            self.started_at_monotonic = time.monotonic()

    def _push_thinking_entry(self, text: str, block_index: int | None) -> None:
        """Coalesce thinking chunks into a single timeline entry per block.

        When ``block_index`` is supplied, consecutive chunks with the
        same index merge; a change in index opens a new timeline entry
        so per-block providers (Gemini, Claude) render with visible
        boundaries. When the provider omits ``block_index`` we fall
        back to the legacy "consecutive thinking events coalesce"
        behaviour so older callers and tests stay green. See #353.
        """
        if self.timeline and self.timeline[-1].get("kind") == "thinking":
            previous_index = self.timeline[-1].get("block_index")
            if block_index is None or previous_index is None or previous_index == block_index:
                self.timeline[-1]["text"] = self.timeline[-1].get("text", "") + text
                return
        entry: dict[str, Any] = {"kind": "thinking", "text": text}
        if block_index is not None:
            entry["block_index"] = block_index
        self.timeline.append(entry)

    def apply(self, event: StreamEvent) -> None:
        """Fold one provider event into the running snapshot."""
        event_type = event.get("type")
        if event_type == "delta":
            self._mark_started()
            self.content += event.get("content", "") or ""
            return
        if event_type == "thinking":
            self._mark_started()
            chunk = event.get("content", "") or ""
            self.thinking += chunk
            self._push_thinking_entry(chunk, event.get("block_index"))
            return
        if event_type == "tool_use":
            self._mark_started()
            tool_use_id = str(event.get("tool_use_id", ""))
            # Redact secrets in the tool input before persistence. The
            # raw stream event is unchanged — only the persisted shape
            # is scrubbed. This matters because ``tool_calls`` is read
            # back into the UI on rehydration and would otherwise show
            # an API key the user pasted verbatim.
            raw_input = dict(event.get("input", {}) or {})
            safe_input = _maybe_redact(raw_input)
            if not isinstance(safe_input, dict):
                safe_input = raw_input
            self.tool_calls.append(
                _ToolCall(
                    id=tool_use_id,
                    name=str(event.get("name", "")),
                    input=safe_input,
                    display=dict(event.get("display", {}) or {}) or None,
                )
            )
            self.timeline.append({"kind": "tool", "toolCallId": tool_use_id})
            return
        if event_type in {"tool_result", "tool_progress"}:
            self._apply_tool_update(event, complete=event_type == "tool_result")
            return
        if event_type == "error":
            self.error_text = event.get("content") or "Chat stream failed."
            return
        if event_type == "usage":
            # Token / cost accounting (PR 04). Providers emit one
            # ``usage`` event per turn on their terminal envelope;
            # multiple turns within a single ``stream()`` call sum.
            self.total_input_tokens += int(event.get("input_tokens", 0) or 0)
            self.total_output_tokens += int(event.get("output_tokens", 0) or 0)
            self.total_cost_usd += float(event.get("cost_usd", 0.0) or 0.0)

    def _apply_tool_update(self, event: StreamEvent, *, complete: bool) -> None:
        """Apply terminal or non-terminal tool output to a tracked call."""
        tool_use_id = str(event.get("tool_use_id", ""))
        for call in self.tool_calls:
            if call.id == tool_use_id:
                call.result = event.get("content")
                if complete:
                    call.status = "completed"
                break

    def duration_seconds(self) -> int:
        """Whole-second elapsed time since the first delta/thinking/tool event."""
        if self.started_at_monotonic is None:
            return 0
        elapsed = time.monotonic() - self.started_at_monotonic
        return max(0, round(elapsed))

    def persisted_thinking_duration_seconds(self) -> int | None:
        """Return the duration value persisted for the assistant turn.

        Fast single-block thinking can complete in less than half a
        second, which rounds to ``0``.  Persist ``1`` in that case so a
        turn that visibly streamed thinking does not rehydrate as if no
        thinking duration was recorded.
        """
        duration = self.duration_seconds()
        if self.thinking and duration <= 0:
            return 1
        return duration or None

    def to_persisted_shape(self, *, status: str) -> dict[str, Any]:
        """Snapshot in the shape ``finalize_assistant_message`` expects."""
        # Use error_text as the rendered content on failed turns so the UI gets
        # the same "Error: ..." string it would have shown live.
        if status == "failed" and self.error_text and not self.content:
            content = f"Error: {self.error_text}"
        else:
            content = self.content
        return {
            "content": content,
            "thinking": self.thinking or None,
            "tool_calls": [call.to_dict() for call in self.tool_calls] or None,
            "timeline": list(self.timeline) or None,
            "thinking_duration_seconds": self.persisted_thinking_duration_seconds(),
            "assistant_status": status,
        }
