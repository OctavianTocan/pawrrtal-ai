"""Span recorder classes for ``app.infrastructure.observability.workshop``.

Holds the mutable per-span state (streamed deltas, buffered tool calls,
final usage) that the ``llm_span`` / ``tool_span`` context managers
stamp onto their OTel spans.  Split out so the public ``workshop``
module stays inside the project's file-line budget
(``scripts/check-file-lines.mjs``); private to the package.
"""

from __future__ import annotations

import time
from typing import Any

from opentelemetry.trace import Span, Status, StatusCode

from app.infrastructure.observability._schema import (
    ATTR_GENAI_COST_USD,
    ATTR_GENAI_FINISH_REASONS,
    ATTR_GENAI_INPUT_TOKENS,
    ATTR_GENAI_OUTPUT_MESSAGES,
    ATTR_GENAI_OUTPUT_TOKENS,
    ATTR_GENAI_RESPONSE_MODEL,
    ATTR_OTEL_STATUS_MESSAGE,
    ATTR_PAWRRTAL_LLM_DURATION_MS,
    ATTR_PAWRRTAL_LLM_TTFT_MS,
    ATTR_PAWRRTAL_TURN_DURATION_MS,
    ATTR_PAWRRTAL_TURN_TTFT_MS,
    ATTR_TRACELOOP_OUTPUT,
    EVENT_ATTR_CONTENT_TEXT,
    EVENT_ATTR_THINKING_TEXT,
    EVENT_CONTENT_DELTA,
    EVENT_THINKING_DELTA,
    json_dumps,
)

_MS_PER_SECOND = 1000.0


class LLMSpanRecorder:
    """Accumulates streamed deltas + final usage onto the live LLM span.

    Workshop's adapter reads ``gen_ai.output.messages`` once the span
    closes, so we buffer the text + tool-call parts in memory and
    stamp the attribute on ``flush()``.  Per-delta events also go on
    the span as OTel span events so Workshop's live websocket
    broadcast surfaces them while the turn is still running.

    The recorder is intentionally tolerant of partial input — each
    method short-circuits on an empty payload so a misbehaving
    provider stream can't crash observability.
    """

    def __init__(self, span: Span, *, model_id: str) -> None:
        """Bind the recorder to *span* and remember the model id."""
        self._span = span
        self._model_id = model_id
        self._text_parts: list[str] = []
        self._thinking_parts: list[str] = []
        self._tool_calls: list[dict[str, Any]] = []
        self._finalised = False
        # Latency clocks — wall-clock perf_counter at recorder build time
        # (i.e. when the provider stream is about to start) and the
        # elapsed time to the first user-visible chunk.  ``_ttft_ms`` is
        # only stamped on the span when it's actually been observed —
        # an LLM span that errored before any token must not lie about
        # having a sub-zero TTFT.
        self._started_at = time.perf_counter()
        self._ttft_ms: float | None = None

    def _mark_first_token(self) -> None:
        """Capture wall-clock elapsed at the first streamed token.

        Idempotent — only the first call wins.  Called from both
        ``record_text_delta`` and ``record_thinking_delta`` so reasoning
        models that emit thinking before any text still get a TTFT.
        """
        if self._ttft_ms is not None:
            return
        self._ttft_ms = (time.perf_counter() - self._started_at) * _MS_PER_SECOND

    def record_text_delta(self, text: str) -> None:
        """Append a streamed text chunk and emit a span event."""
        if not text:
            return
        self._mark_first_token()
        self._text_parts.append(text)
        self._span.add_event(EVENT_CONTENT_DELTA, {EVENT_ATTR_CONTENT_TEXT: text})

    def record_thinking_delta(self, text: str) -> None:
        """Append a streamed reasoning chunk and emit a span event."""
        if not text:
            return
        self._mark_first_token()
        self._thinking_parts.append(text)
        self._span.add_event(EVENT_THINKING_DELTA, {EVENT_ATTR_THINKING_TEXT: text})

    def record_tool_call(
        self,
        *,
        tool_call_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> None:
        """Buffer a tool-call part for the final ``gen_ai.output.messages``."""
        self._tool_calls.append(
            {
                "type": "tool_call",
                "id": tool_call_id,
                "name": name,
                "arguments": arguments,
            }
        )

    def record_usage(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float | None,
    ) -> None:
        """Stamp the terminal usage block onto the span."""
        self._span.set_attribute(ATTR_GENAI_INPUT_TOKENS, int(input_tokens))
        self._span.set_attribute(ATTR_GENAI_OUTPUT_TOKENS, int(output_tokens))
        if cost_usd is not None:
            self._span.set_attribute(ATTR_GENAI_COST_USD, float(cost_usd))

    def record_stop(self, stop_reason: str) -> None:
        """Stamp the terminal stop reason (``"stop"``, ``"tool_use"``, ...)."""
        if not stop_reason:
            return
        self._span.set_attribute(ATTR_GENAI_FINISH_REASONS, json_dumps([stop_reason]))

    def record_error(self, message: str) -> None:
        """Mark the span as errored and stamp the message.

        Called by ``llm_span``'s ``except`` clause; tests may call it
        directly to verify the error path without raising.
        """
        self._span.set_status(Status(StatusCode.ERROR, message))
        self._span.set_attribute(ATTR_OTEL_STATUS_MESSAGE, message)

    @property
    def ttft_ms(self) -> float | None:
        """Time to first token in milliseconds, or ``None`` if no token streamed."""
        return self._ttft_ms

    def flush(self) -> None:
        """Stamp ``gen_ai.output.messages`` + ``gen_ai.response.model``.

        Idempotent — the LLM span context-manager calls this in its
        ``finally`` block so an exception path still gets a partial
        output stamped (the text accumulated up to the failure).  The
        same call also stamps the ``pawrrtal.llm.*`` latency attributes
        so a failed turn still gets its observed latency on the span.
        """
        if self._finalised:
            return
        self._finalised = True
        parts: list[dict[str, Any]] = []
        if self._text_parts:
            parts.append({"type": "text", "content": "".join(self._text_parts)})
        parts.extend(self._tool_calls)
        self._span.set_attribute(ATTR_GENAI_RESPONSE_MODEL, self._model_id)
        self._span.set_attribute(
            ATTR_GENAI_OUTPUT_MESSAGES,
            json_dumps([{"role": "assistant", "parts": parts}]),
        )
        duration_ms = (time.perf_counter() - self._started_at) * _MS_PER_SECOND
        self._span.set_attribute(ATTR_PAWRRTAL_LLM_DURATION_MS, float(duration_ms))
        if self._ttft_ms is not None:
            self._span.set_attribute(ATTR_PAWRRTAL_LLM_TTFT_MS, float(self._ttft_ms))


class TurnSpanRecorder:
    """Tracks turn-level latency and stamps it on the turn span.

    Mirrors :class:`LLMSpanRecorder`'s contract for the outer
    ``pawrrtal.turn`` span: the recorder is constructed when the turn
    starts, callers ping :meth:`record_first_event` as soon as the
    first user-visible chunk is produced, and :meth:`flush` stamps the
    final ``pawrrtal.turn.duration_ms`` (always) and
    ``pawrrtal.turn.ttft_ms`` (when a first event was observed).
    Workshop's UI ignores attributes it doesn't recognise, so this is
    safe to emit alongside the existing turn-span attributes.
    """

    def __init__(self, span: Span) -> None:
        """Bind the recorder to *span* and start the latency clock."""
        self._span = span
        self._started_at = time.perf_counter()
        self._ttft_ms: float | None = None
        self._finalised = False

    def record_first_event(self) -> None:
        """Mark the moment the first user-visible event was emitted.

        Idempotent — only the first call wins.  Called from the turn
        runner's event hook so any event type (delta, thinking,
        tool_use, message, error) counts as "first byte to the user".
        """
        if self._ttft_ms is not None:
            return
        self._ttft_ms = (time.perf_counter() - self._started_at) * _MS_PER_SECOND

    @property
    def ttft_ms(self) -> float | None:
        """Time to first user-visible event in milliseconds, or ``None``."""
        return self._ttft_ms

    def flush(self) -> None:
        """Stamp ``pawrrtal.turn.duration_ms`` and ``pawrrtal.turn.ttft_ms``.

        Idempotent — repeated calls are no-ops so a caller can safely
        invoke this in a ``finally`` block.  The recorder computes its
        own duration from the wall-clock captured at construction so it
        doesn't need to be threaded through the turn runner.
        """
        if self._finalised:
            return
        self._finalised = True
        duration_ms = (time.perf_counter() - self._started_at) * _MS_PER_SECOND
        self._span.set_attribute(ATTR_PAWRRTAL_TURN_DURATION_MS, float(duration_ms))
        if self._ttft_ms is not None:
            self._span.set_attribute(ATTR_PAWRRTAL_TURN_TTFT_MS, float(self._ttft_ms))


class ToolSpanRecorder:
    """Stamps the tool result onto its span at finish time."""

    def __init__(self, span: Span) -> None:
        """Bind the recorder to *span*."""
        self._span = span

    def record_result(self, result: Any, *, is_error: bool) -> None:
        """Stamp ``traceloop.entity.output`` and propagate error status."""
        self._span.set_attribute(ATTR_TRACELOOP_OUTPUT, json_dumps(result))
        if is_error:
            self._span.set_status(Status(StatusCode.ERROR))
            self._span.set_attribute(ATTR_OTEL_STATUS_MESSAGE, str(result))

    def record_error(self, message: str) -> None:
        """Mark the span as errored and stamp the message as the output."""
        self._span.set_status(Status(StatusCode.ERROR, message))
        self._span.set_attribute(ATTR_OTEL_STATUS_MESSAGE, message)
        self._span.set_attribute(
            ATTR_TRACELOOP_OUTPUT,
            json_dumps({"error": message}),
        )
