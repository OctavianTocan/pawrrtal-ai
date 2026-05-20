"""Workshop-compatible OTel spans for the Pawrrtal agent loop and tools.

`Raindrop Workshop`_ is a localhost OTLP collector (default
``http://localhost:5899``) that renders an agent's tokens, tool calls, and
turn boundaries live as the loop runs.  It ingests OTLP/HTTP-JSON at
``/v1/traces`` and parses three vendor schemas: Vercel AI SDK, Claude
Agent SDK, and OpenLLMetry / Traceloop semantic conventions.

This module emits the **Traceloop / OpenLLMetry** flavour because that is
the OTel community baseline (``gen_ai.*`` attributes) — it works in
Workshop *and* every other OTel backend (Grafana, Honeycomb, SigNoz,
Tempo, Jaeger).  No vendor-specific wire protocol; no extra dependency
beyond the OTel SDK already pulled in by ``app.core.telemetry``.

Schema we emit (see workshop/src/spans/adapters/traceloop.ts for the
parser side):

* **Turn span** — root for one chat turn.
    Attributes: ``pawrrtal.conversation_id``, ``pawrrtal.user_id``,
    ``pawrrtal.surface``, ``pawrrtal.request_id``,
    ``gen_ai.request.model``.

* **LLM span** (``traceloop.span.kind = "llm"``) — attributes:
  ``gen_ai.operation.name = "chat"``;
  ``gen_ai.request.model`` / ``gen_ai.response.model``;
  ``gen_ai.input.messages`` (JSON string);
  ``gen_ai.output.messages`` (JSON string, stamped on flush);
  ``gen_ai.system_instructions`` (JSON string, optional);
  ``gen_ai.usage.input_tokens`` / ``gen_ai.usage.output_tokens``;
  ``gen_ai.response.finish_reasons`` (JSON string).
  Span events: ``gen_ai.content.delta`` per streamed text chunk;
  ``gen_ai.thinking.delta`` per streamed reasoning chunk.

* **Tool span** (``traceloop.span.kind = "tool"``) — attributes:
  ``traceloop.entity.name`` (tool name — Workshop's display key);
  ``traceloop.entity.input``  (JSON string of arguments);
  ``traceloop.entity.output`` (JSON string of result);
  ``otel.status.message``     (error string on failure).

All recorders are no-ops when telemetry is disabled — the underlying
``trace.get_tracer`` returns a no-op tracer when
``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset (see
``app.core.telemetry.setup_tracing``).  Importing this module is safe
in tests and bare installs.

.. _Raindrop Workshop: https://github.com/raindrop-ai/workshop
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.core.observability._recorders import (
    LLMSpanRecorder,
    ToolSpanRecorder,
    TurnSpanRecorder,
)
from app.core.observability._schema import (
    ATTR_CONVERSATION_ID,
    ATTR_GENAI_INPUT_MESSAGES,
    ATTR_GENAI_OPERATION,
    ATTR_GENAI_REQUEST_MODEL,
    ATTR_GENAI_SYSTEM_INSTRUCTIONS,
    ATTR_OTEL_STATUS_MESSAGE,
    ATTR_REQUEST_ID,
    ATTR_SURFACE,
    ATTR_TOOL_CALL_ID,
    ATTR_TRACELOOP_INPUT,
    ATTR_TRACELOOP_KIND,
    ATTR_TRACELOOP_NAME,
    ATTR_USER_ID,
    KIND_LLM,
    KIND_TOOL,
    STREAM_TYPE_DELTA,
    STREAM_TYPE_ERROR,
    STREAM_TYPE_THINKING,
    STREAM_TYPE_TOOL_USE,
    STREAM_TYPE_USAGE,
    TRACER_NAME,
    TRACER_VERSION,
    json_dumps,
    render_input_messages,
)

if TYPE_CHECKING:
    from app.core.agent_loop.types import AgentMessage
    from app.core.providers.base import StreamEvent

__all__ = [
    "LLMSpanRecorder",
    "ToolSpanRecorder",
    "TurnSpanRecorder",
    "llm_span",
    "reset_tracer_for_tests",
    "set_tracer_for_tests",
    "tool_span",
    "turn_span",
    "workshop_event_hook",
]

_tracer = trace.get_tracer(TRACER_NAME, TRACER_VERSION)

# Test-injectable tracer override (#352 L6). When non-``None``, every
# span recorder reads spans through this tracer instead of the
# global ``_tracer``. ``InMemorySpanExporter``-based tests inject
# their own provider's tracer here, so the test never has to swap
# the global ``trace.set_tracer_provider`` (which is one-shot per
# process and produces order-dependent flakes in pytest fixtures).
_tracer_override: trace.Tracer | None = None


def _active_tracer() -> trace.Tracer:
    """Return the test-injected tracer when set, otherwise the module tracer.

    Every span context manager in this module reads through this
    helper so the override is a single seam — there's no chance a
    new code path forgets to consult it.
    """
    return _tracer_override if _tracer_override is not None else _tracer


def set_tracer_for_tests(tracer: trace.Tracer) -> None:
    """Install a test tracer so OTel assertions stay local to the test.

    Pair with :func:`reset_tracer_for_tests` in a ``finally`` /
    ``addfinalizer`` so the override doesn't leak across tests.

    Args:
        tracer: A tracer (typically built from a per-test
            ``TracerProvider`` + ``InMemorySpanExporter``) that
            captures spans into an exporter the test can read back.
    """
    global _tracer_override  # noqa: PLW0603 — test seam by design
    _tracer_override = tracer


def reset_tracer_for_tests() -> None:
    """Clear the test tracer so subsequent spans use the module default."""
    global _tracer_override  # noqa: PLW0603 — test seam by design
    _tracer_override = None

# Per-conversation memory of the previous turn's span context so
# successive turns in the same conversation are linked.  OTel span
# links are the standard way to connect traces without forcing them
# into a single parent-child tree — backends like Grafana and Jaeger
# surface them as "related traces".  Bounded to avoid unbounded growth
# in long-running processes; entries are evicted FIFO.
_MAX_LINKED_CONVERSATIONS = 1024
_previous_turn: dict[str, trace.SpanContext] = {}


@contextmanager
def turn_span(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    surface: str,
    request_id: str,
    model_id: str | None,
) -> Iterator[TurnSpanRecorder]:
    """Root span for one chat turn.

    Every LLM and tool span emitted inside this context-manager inherits
    the same ``trace_id``, so Workshop groups them as one "run" (see
    workshop/src/server.ts → ``upsertRun`` keyed by trace_id).

    The yielded :class:`TurnSpanRecorder` carries the latency clocks:
    callers ping :meth:`TurnSpanRecorder.record_first_event` from the
    event hook so ``pawrrtal.turn.ttft_ms`` lands on the span, and the
    recorder ``flush()`` call (in the ``finally`` here) stamps
    ``pawrrtal.turn.duration_ms``.

    Args:
        conversation_id: Pawrrtal conversation UUID.
        user_id: Authenticated user UUID.
        surface: Origin surface — ``"WEB"``, ``"TELEGRAM"``, etc.
            Matches the chat router's ``log_tag``.
        request_id: Request correlation ID from ``request_logging``.
        model_id: Provider-qualified model identifier
            (e.g. ``"gemini:gemini-2.0-flash-exp"``) when known.

    Yields:
        A :class:`TurnSpanRecorder` so callers can mark TTFT and read
        it back for the canonical log line / event-bus payload.
    """
    conv_key = str(conversation_id)
    # If this conversation had a previous turn, link to it so backends
    # can chain the traces and Workshop shows "related runs".
    prev_ctx = _previous_turn.get(conv_key)
    links = [trace.Link(prev_ctx)] if prev_ctx is not None else None

    with _active_tracer().start_as_current_span("pawrrtal.turn", links=links) as span:
        span.set_attribute(ATTR_CONVERSATION_ID, conv_key)
        span.set_attribute(ATTR_USER_ID, str(user_id))
        span.set_attribute(ATTR_SURFACE, surface)
        span.set_attribute(ATTR_REQUEST_ID, request_id)
        if model_id:
            span.set_attribute(ATTR_GENAI_REQUEST_MODEL, model_id)
        recorder = TurnSpanRecorder(span)
        # Remember this turn's context so the next turn in the same
        # conversation can link back to it.
        if span.is_recording():
            if len(_previous_turn) >= _MAX_LINKED_CONVERSATIONS:
                _previous_turn.pop(next(iter(_previous_turn)))
            _previous_turn[conv_key] = span.get_span_context()
        try:
            yield recorder
        finally:
            recorder.flush()


@contextmanager
def llm_span(
    *,
    model_id: str,
    messages: list[AgentMessage],
    system_prompt: str | None,
) -> Iterator[LLMSpanRecorder]:
    """Span for one LLM call.

    Workshop's UI renders the panel from ``gen_ai.input.messages`` (the
    canonical messages list) and ``gen_ai.output.messages`` (stamped on
    flush), with per-token rows from the ``gen_ai.content.delta`` span
    events.  Errors raised inside the context-manager are recorded on
    the span (``Status.ERROR`` + ``otel.status.message``) before
    re-raising so a failed turn still shows up as a red row in
    Workshop's run list.

    Args:
        model_id: Provider-qualified model identifier (used for both
            ``gen_ai.request.model`` and the final
            ``gen_ai.response.model`` attribute).
        messages: Conversation history + the new user turn — the same
            shape the agent loop accumulates.  Rendered into the
            canonical OpenLLMetry ``parts`` schema.
        system_prompt: Workspace system prompt, if any.  Stored as
            ``gen_ai.system_instructions`` so Workshop's panel can show
            it above the conversation.

    Yields:
        An ``LLMSpanRecorder`` whose ``record_*`` methods accumulate
        streamed tokens and stamp final attributes on ``flush()``.
    """
    with _active_tracer().start_as_current_span("pawrrtal.llm.chat") as span:
        span.set_attribute(ATTR_TRACELOOP_KIND, KIND_LLM)
        span.set_attribute(ATTR_GENAI_OPERATION, "chat")
        span.set_attribute(ATTR_GENAI_REQUEST_MODEL, model_id)
        span.set_attribute(
            ATTR_GENAI_INPUT_MESSAGES,
            json_dumps(render_input_messages(messages)),
        )
        if system_prompt:
            span.set_attribute(
                ATTR_GENAI_SYSTEM_INSTRUCTIONS,
                json_dumps([{"type": "text", "content": system_prompt}]),
            )
        recorder = LLMSpanRecorder(span, model_id=model_id)
        try:
            yield recorder
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.set_attribute(ATTR_OTEL_STATUS_MESSAGE, str(exc))
            raise
        finally:
            recorder.flush()


@contextmanager
def tool_span(
    *,
    name: str,
    tool_call_id: str,
    arguments: dict[str, Any],
) -> Iterator[ToolSpanRecorder]:
    """Span for one tool execution.

    Workshop renders these as collapsible rows with the args + result
    side-by-side.  Failures are recorded with ``Status.ERROR`` and
    ``otel.status.message`` so the row is highlighted in the timeline.

    The span name is ``"<tool_name>.tool"`` to match Traceloop's
    convention (Workshop strips the ``.tool`` suffix when picking the
    display name; see workshop/src/spans/adapters/traceloop.ts).

    Args:
        name: Tool name as registered in the agent loop's tool map.
        tool_call_id: Stable correlation ID from the provider, used to
            pair this span with its surrounding LLM span in the
            Workshop UI.
        arguments: The kwargs the model produced for the tool.  Stored
            as JSON so Workshop's renderer can show the parameter tree.

    Yields:
        A ``ToolSpanRecorder`` — call ``record_result`` (or
        ``record_error``) before the context exits to stamp the output.
    """
    with _active_tracer().start_as_current_span(f"{name}.tool") as span:
        span.set_attribute(ATTR_TRACELOOP_KIND, KIND_TOOL)
        span.set_attribute(ATTR_TRACELOOP_NAME, name)
        span.set_attribute(ATTR_TRACELOOP_INPUT, json_dumps(arguments))
        span.set_attribute(ATTR_TOOL_CALL_ID, tool_call_id)
        recorder = ToolSpanRecorder(span)
        try:
            yield recorder
        except Exception as exc:
            recorder.record_error(str(exc))
            raise


def _hook_delta(recorder: LLMSpanRecorder, event: StreamEvent) -> None:
    recorder.record_text_delta(event.get("content", ""))


def _hook_thinking(recorder: LLMSpanRecorder, event: StreamEvent) -> None:
    recorder.record_thinking_delta(event.get("content", ""))


def _hook_tool_use(recorder: LLMSpanRecorder, event: StreamEvent) -> None:
    recorder.record_tool_call(
        tool_call_id=event.get("tool_use_id", ""),
        name=event.get("name", ""),
        arguments=event.get("input", {}) or {},
    )


def _hook_usage(recorder: LLMSpanRecorder, event: StreamEvent) -> None:
    recorder.record_usage(
        input_tokens=event.get("input_tokens", 0) or 0,
        output_tokens=event.get("output_tokens", 0) or 0,
        cost_usd=event.get("cost_usd"),
    )


def _hook_error(recorder: LLMSpanRecorder, event: StreamEvent) -> None:
    recorder.record_error(event.get("content", "stream error"))


# Dispatch table for ``workshop_event_hook`` — flat ``str → handler`` map
# instead of an if/elif ladder so the function stays inside the project's
# nesting-depth budget (``scripts/check-nesting.py``).  Unknown event
# types are silently ignored — observability must never crash a chat
# turn if a provider introduces a new ``StreamEvent`` type.
_HOOK_DISPATCH: dict[str, Callable[[LLMSpanRecorder, StreamEvent], None]] = {
    STREAM_TYPE_DELTA: _hook_delta,
    STREAM_TYPE_THINKING: _hook_thinking,
    STREAM_TYPE_TOOL_USE: _hook_tool_use,
    STREAM_TYPE_USAGE: _hook_usage,
    STREAM_TYPE_ERROR: _hook_error,
}


def workshop_event_hook(
    recorder: LLMSpanRecorder,
    *,
    turn_recorder: TurnSpanRecorder | None = None,
) -> Callable[[StreamEvent], list[StreamEvent]]:
    """Return a ``turn_runner.EventHook`` that mirrors stream events onto *recorder*.

    The hook is read-only — it always returns ``[]`` so the upstream
    chat aggregator + channel deliverer see the original stream
    unchanged.  It exists so the channel turn-runner can keep its
    instrumentation layered side-by-side with the rest of its
    ``event_hooks`` list (existing seam at ``turn_runner.py``: ``EventHook
    = Callable[[StreamEvent], list[StreamEvent]]``).

    Dispatch is via :data:`_HOOK_DISPATCH` so the closure stays flat —
    important for the project's nesting-depth gate.

    When *turn_recorder* is supplied, every observed event also pings
    :meth:`TurnSpanRecorder.record_first_event` so the outer turn span
    gets its TTFT — including error / message / tool_use events that
    don't carry through to :class:`LLMSpanRecorder`.

    Args:
        recorder: The LLM span recorder for the current turn.  Usually
            obtained from ``with llm_span(...) as recorder``.
        turn_recorder: Optional outer-turn recorder.  When provided,
            the hook also marks turn-level TTFT on first event.

    Returns:
        A pure function consumable by ``run_turn(event_hooks=...)``.
    """

    def hook(event: StreamEvent) -> list[StreamEvent]:
        if turn_recorder is not None:
            turn_recorder.record_first_event()
        handler = _HOOK_DISPATCH.get(event.get("type", ""))
        if handler is not None:
            handler(recorder, event)
        return []

    return hook
