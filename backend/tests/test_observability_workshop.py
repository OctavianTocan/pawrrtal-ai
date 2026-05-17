"""Unit tests for ``app.core.observability.workshop``.

The recorders are exercised against an in-memory OTel ``TracerProvider``
so each test captures the spans that were emitted and asserts on the
exact Workshop attribute shape (``traceloop.span.kind``,
``gen_ai.input.messages``, etc.).  This is the canonical pattern for
testing OTel-emitting code — recommended in the official `OTel testing
docs`_ — and means the tests don't need a live Workshop daemon to
verify the wire contract.

Reference: workshop/src/spans/adapters/traceloop.ts — the parser these
spans target.  Each assertion lines up with one of its attribute reads
so a future Workshop schema change shows up as a test failure here
rather than silently breaking the UI rendering.

.. _OTel testing docs: https://opentelemetry-python.readthedocs.io/
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.observability import workshop as workshop_module
from app.core.observability._recorders import TurnSpanRecorder
from app.core.observability.workshop import (
    llm_span,
    tool_span,
    turn_span,
    workshop_event_hook,
)


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    """Install an in-memory OTel exporter for the duration of one test.

    The workshop module caches its tracer at import time, so we have
    to repoint that cached tracer at our provider as well — otherwise
    the recorders write to the global no-op tracer and nothing gets
    captured.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    previous_provider = trace.get_tracer_provider()
    previous_module_tracer = workshop_module._tracer
    trace.set_tracer_provider(provider)
    workshop_module._tracer = provider.get_tracer("test")
    try:
        yield exporter
    finally:
        workshop_module._tracer = previous_module_tracer
        # set_tracer_provider on the global is technically one-shot;
        # restoring it is best-effort so tests don't leak state.
        trace.set_tracer_provider(previous_provider)
        provider.shutdown()


def _attrs(span: ReadableSpan) -> dict[str, object]:
    """Return a plain dict view of a span's attributes (or ``{}``)."""
    return dict(span.attributes or {})


def _span_by_name(exporter: InMemorySpanExporter, name: str) -> ReadableSpan:
    """Return the (single) span with *name* or raise ``AssertionError``."""
    matches = [s for s in exporter.get_finished_spans() if s.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r} span, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# turn_span
# ---------------------------------------------------------------------------


def test_turn_span_attaches_pawrrtal_attributes(span_exporter: InMemorySpanExporter) -> None:
    """``turn_span`` stamps the conversation / user / surface tuple."""
    conversation_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with turn_span(
        conversation_id=conversation_id,
        user_id=user_id,
        surface="WEB",
        request_id="req-123",
        model_id="gemini:gemini-2.0-flash-exp",
    ):
        pass

    span = _span_by_name(span_exporter, "pawrrtal.turn")
    attrs = _attrs(span)
    assert attrs["pawrrtal.conversation_id"] == str(conversation_id)
    assert attrs["pawrrtal.user_id"] == str(user_id)
    assert attrs["pawrrtal.surface"] == "WEB"
    assert attrs["pawrrtal.request_id"] == "req-123"
    assert attrs["gen_ai.request.model"] == "gemini:gemini-2.0-flash-exp"


def test_turn_span_omits_model_when_none(span_exporter: InMemorySpanExporter) -> None:
    """A missing model id is omitted, not stamped as ``"None"``."""
    with turn_span(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        surface="TELEGRAM",
        request_id="",
        model_id=None,
    ):
        pass

    span = _span_by_name(span_exporter, "pawrrtal.turn")
    assert "gen_ai.request.model" not in _attrs(span)


# ---------------------------------------------------------------------------
# llm_span
# ---------------------------------------------------------------------------


def test_llm_span_emits_traceloop_kind_and_input_messages(
    span_exporter: InMemorySpanExporter,
) -> None:
    """The span carries Workshop's Traceloop discriminator + canonical input shape."""
    with llm_span(
        model_id="claude:sonnet-4.6",
        messages=[{"role": "user", "content": "What's the time?"}],
        system_prompt="Be concise.",
    ):
        pass

    span = _span_by_name(span_exporter, "pawrrtal.llm.chat")
    attrs = _attrs(span)
    assert attrs["traceloop.span.kind"] == "llm"
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.request.model"] == "claude:sonnet-4.6"

    input_payload = json.loads(str(attrs["gen_ai.input.messages"]))
    assert input_payload == [
        {
            "role": "user",
            "parts": [{"type": "text", "content": "What's the time?"}],
        }
    ]

    system_payload = json.loads(str(attrs["gen_ai.system_instructions"]))
    assert system_payload == [{"type": "text", "content": "Be concise."}]


def test_llm_span_renders_assistant_tool_call_history(
    span_exporter: InMemorySpanExporter,
) -> None:
    """Assistant turns with tool calls survive the canonical translation."""
    messages = [
        {"role": "user", "content": "Search please."},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "On it."},
                {
                    "type": "toolCall",
                    "tool_call_id": "tc-1",
                    "name": "search",
                    "arguments": {"q": "python async"},
                },
            ],
            "stop_reason": "tool_use",
        },
        {
            "role": "toolResult",
            "tool_call_id": "tc-1",
            "content": [{"type": "text", "text": "found 3 results"}],
            "is_error": False,
        },
    ]

    with llm_span(model_id="m", messages=messages, system_prompt=None):
        pass

    span = _span_by_name(span_exporter, "pawrrtal.llm.chat")
    payload = json.loads(str(_attrs(span)["gen_ai.input.messages"]))
    assert payload[0]["role"] == "user"
    assert payload[1]["role"] == "assistant"
    assert payload[1]["parts"][1] == {
        "type": "tool_call",
        "id": "tc-1",
        "name": "search",
        "arguments": {"q": "python async"},
    }
    assert payload[2]["role"] == "tool"
    assert payload[2]["parts"][0]["content"] == "found 3 results"


def test_llm_recorder_accumulates_deltas_and_stamps_output_on_flush(
    span_exporter: InMemorySpanExporter,
) -> None:
    """Streamed text + tool calls show up in ``gen_ai.output.messages``."""
    with llm_span(model_id="m", messages=[], system_prompt=None) as recorder:
        recorder.record_text_delta("Hello, ")
        recorder.record_text_delta("world!")
        recorder.record_tool_call(
            tool_call_id="tc-7",
            name="search",
            arguments={"q": "kittens"},
        )
        recorder.record_usage(input_tokens=10, output_tokens=4, cost_usd=0.0123)
        recorder.record_stop("tool_use")

    span = _span_by_name(span_exporter, "pawrrtal.llm.chat")
    attrs = _attrs(span)
    output = json.loads(str(attrs["gen_ai.output.messages"]))
    assert output == [
        {
            "role": "assistant",
            "parts": [
                {"type": "text", "content": "Hello, world!"},
                {
                    "type": "tool_call",
                    "id": "tc-7",
                    "name": "search",
                    "arguments": {"q": "kittens"},
                },
            ],
        }
    ]
    assert attrs["gen_ai.response.model"] == "m"
    assert attrs["gen_ai.usage.input_tokens"] == 10
    assert attrs["gen_ai.usage.output_tokens"] == 4
    assert attrs["gen_ai.usage.cost_usd"] == pytest.approx(0.0123)
    assert json.loads(str(attrs["gen_ai.response.finish_reasons"])) == ["tool_use"]


def test_llm_recorder_emits_span_events_per_delta(
    span_exporter: InMemorySpanExporter,
) -> None:
    """Each text + thinking delta becomes a span event so Workshop's live UI updates."""
    with llm_span(model_id="m", messages=[], system_prompt=None) as recorder:
        recorder.record_thinking_delta("hmm")
        recorder.record_text_delta("answer")
        recorder.record_text_delta("")  # empty chunk should be ignored

    span = _span_by_name(span_exporter, "pawrrtal.llm.chat")
    event_names = [e.name for e in span.events]
    assert event_names == ["gen_ai.thinking.delta", "gen_ai.content.delta"]


def test_llm_span_records_exception_status(span_exporter: InMemorySpanExporter) -> None:
    """An exception inside the LLM span flushes a partial output and marks the span errored."""

    def _run() -> None:
        with llm_span(model_id="m", messages=[], system_prompt=None) as recorder:
            recorder.record_text_delta("partial")
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _run()

    span = _span_by_name(span_exporter, "pawrrtal.llm.chat")
    assert span.status.status_code == trace.StatusCode.ERROR
    attrs = _attrs(span)
    assert attrs["otel.status.message"] == "boom"
    output = json.loads(str(attrs["gen_ai.output.messages"]))
    assert output[0]["parts"][0]["content"] == "partial"


# ---------------------------------------------------------------------------
# tool_span
# ---------------------------------------------------------------------------


def test_tool_span_records_input_and_output(span_exporter: InMemorySpanExporter) -> None:
    """``tool_span`` stamps Traceloop-shaped args + result for a successful call."""
    with tool_span(name="search", tool_call_id="tc-1", arguments={"q": "x"}) as ts:
        ts.record_result({"hits": 3}, is_error=False)

    span = _span_by_name(span_exporter, "search.tool")
    attrs = _attrs(span)
    assert attrs["traceloop.span.kind"] == "tool"
    assert attrs["traceloop.entity.name"] == "search"
    assert json.loads(str(attrs["traceloop.entity.input"])) == {"q": "x"}
    assert json.loads(str(attrs["traceloop.entity.output"])) == {"hits": 3}
    assert attrs["pawrrtal.tool_call_id"] == "tc-1"
    assert span.status.status_code != trace.StatusCode.ERROR


def test_tool_span_marks_errored_on_is_error_true(
    span_exporter: InMemorySpanExporter,
) -> None:
    """``is_error=True`` flips the span to ``StatusCode.ERROR`` with the message."""
    with tool_span(name="search", tool_call_id="tc-1", arguments={}) as ts:
        ts.record_result("Tool 'search' not found.", is_error=True)

    span = _span_by_name(span_exporter, "search.tool")
    assert span.status.status_code == trace.StatusCode.ERROR
    assert _attrs(span)["otel.status.message"] == "Tool 'search' not found."


def test_tool_span_records_exception(span_exporter: InMemorySpanExporter) -> None:
    """An unexpected exception inside ``tool_span`` is captured on the span."""

    def _run() -> None:
        with tool_span(name="search", tool_call_id="tc-1", arguments={}):
            raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match="kaboom"):
        _run()

    span = _span_by_name(span_exporter, "search.tool")
    assert span.status.status_code == trace.StatusCode.ERROR
    attrs = _attrs(span)
    assert attrs["otel.status.message"] == "kaboom"
    assert json.loads(str(attrs["traceloop.entity.output"])) == {"error": "kaboom"}


# ---------------------------------------------------------------------------
# workshop_event_hook
# ---------------------------------------------------------------------------


def test_event_hook_mirrors_stream_events_onto_recorder(
    span_exporter: InMemorySpanExporter,
) -> None:
    """The hook is read-only and feeds every relevant ``StreamEvent`` into the recorder."""
    with llm_span(model_id="m", messages=[], system_prompt=None) as recorder:
        hook = workshop_event_hook(recorder)
        assert hook({"type": "delta", "content": "Hi"}) == []
        assert hook({"type": "thinking", "content": "thought"}) == []
        assert (
            hook(
                {
                    "type": "tool_use",
                    "tool_use_id": "tc-9",
                    "name": "search",
                    "input": {"q": "x"},
                }
            )
            == []
        )
        assert (
            hook(
                {
                    "type": "usage",
                    "input_tokens": 7,
                    "output_tokens": 1,
                    "cost_usd": 0.0,
                }
            )
            == []
        )
        # Unknown event types are ignored, not raised.
        assert hook({"type": "unknown"}) == []

    attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.llm.chat"))
    output = json.loads(str(attrs["gen_ai.output.messages"]))
    assistant_parts = output[0]["parts"]
    assert assistant_parts[0] == {"type": "text", "content": "Hi"}
    assert assistant_parts[1] == {
        "type": "tool_call",
        "id": "tc-9",
        "name": "search",
        "arguments": {"q": "x"},
    }
    assert attrs["gen_ai.usage.input_tokens"] == 7


# ---------------------------------------------------------------------------
# turn_runner integration — span layering + history rendering
# ---------------------------------------------------------------------------


def test_build_llm_view_messages_renders_history_and_question() -> None:
    """Conversation history flows into the Workshop ``gen_ai.input.messages`` panel."""
    from app.core.observability._turn_view import build_llm_view_messages

    rendered = build_llm_view_messages(
        history=[
            {"role": "user", "content": "what's 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "and 3+3?"},
            {"role": "assistant", "content": "6"},
        ],
        current_question="finally, 4+4?",
    )

    assert [m["role"] for m in rendered] == ["user", "assistant", "user", "assistant", "user"]
    # Assistant rows render with a single text-content block + synthetic stop reason.
    assistant_one = rendered[1]
    assert assistant_one["role"] == "assistant"  # narrow the AgentMessage union
    assert assistant_one["content"] == [{"type": "text", "text": "4"}]
    assert assistant_one["stop_reason"] == "stop"
    # Current question is appended verbatim as the trailing user turn.
    assert rendered[-1] == {"role": "user", "content": "finally, 4+4?"}


def test_build_llm_view_messages_skips_unknown_roles() -> None:
    """Rows with unexpected roles (system, tool) are dropped, not crash-rendered."""
    from app.core.observability._turn_view import build_llm_view_messages

    rendered = build_llm_view_messages(
        history=[
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "noise"},
            {"role": "tool", "content": "noise"},
            {"role": "assistant", "content": "hello"},
        ],
        current_question="continue please",
    )

    # Only user / assistant rows survive, plus the trailing current question.
    assert [m["role"] for m in rendered] == ["user", "assistant", "user"]


@pytest.mark.anyio
async def test_finalize_turn_errors_do_not_taint_llm_span(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``_finalize_turn`` failure marks the turn span but NOT the LLM span.

    Greptile reviewer flagged the original layout: ``_finalize_turn`` was
    called from inside both ``turn_span`` and ``llm_span``, so a database
    persist failure would bubble through ``llm_span``'s ``except`` clause
    and stamp the LLM call as errored. The fix nests the contexts so
    finalisation runs only inside ``turn_span``.
    """
    import uuid as _uuid

    from app.channels.turn_runner import ChatTurnInput, run_turn

    # Minimal fake provider — yields one delta + one usage event so the
    # aggregator + LLM recorder both have something to flush.
    class _FakeProvider:
        async def stream(self, *_args: object, **_kwargs: object):
            yield {"type": "delta", "content": "hi"}
            yield {
                "type": "usage",
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.0,
            }

    # Minimal fake channel — passes events through as bytes verbatim.
    class _FakeChannel:
        surface = "test"

        async def deliver(self, stream, _message):
            async for event in stream:
                yield str(event).encode()

    channel_message = {
        "user_id": _uuid.uuid4(),
        "conversation_id": _uuid.uuid4(),
        "text": "hello",
        "surface": "test",
        "model_id": "test:fake",
        "metadata": {},
    }

    # Bypass DB persist + finalize. The persist replacement must return
    # a (history, assistant_message_id) tuple so run_turn can proceed
    # past the load step.
    async def _no_persist(_turn_input):
        return [{"role": "user", "content": "prior"}], _uuid.uuid4()

    async def _failing_finalize(**_kwargs):
        raise RuntimeError("simulated DB persist failure")

    monkeypatch.setattr(
        "app.channels.turn_runner._load_history_and_persist",
        _no_persist,
    )
    monkeypatch.setattr(
        "app.channels.turn_runner._finalize_turn",
        _failing_finalize,
    )

    turn_input = ChatTurnInput(
        conversation_id=channel_message["conversation_id"],
        user_id=channel_message["user_id"],
        question="hello",
        provider=_FakeProvider(),  # type: ignore[arg-type]
        channel=_FakeChannel(),  # type: ignore[arg-type]
        channel_message=channel_message,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="simulated DB persist failure"):
        async for _chunk in run_turn(turn_input):
            pass

    llm_chat_span = _span_by_name(span_exporter, "pawrrtal.llm.chat")
    assert llm_chat_span.status.status_code != trace.StatusCode.ERROR, (
        "LLM call succeeded — _finalize_turn DB error must not corrupt its status"
    )
    # The turn span IS expected to capture the failure since the turn
    # itself failed at finalisation.
    turn_span_recorded = _span_by_name(span_exporter, "pawrrtal.turn")
    assert turn_span_recorded.status.status_code == trace.StatusCode.ERROR


@pytest.mark.anyio
async def test_run_turn_passes_history_into_llm_span(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``gen_ai.input.messages`` carries the full conversation, not only the new turn."""
    import uuid as _uuid

    from app.channels.turn_runner import ChatTurnInput, run_turn

    class _FakeProvider:
        async def stream(self, *_args: object, **_kwargs: object):
            yield {"type": "delta", "content": "ack"}

    class _FakeChannel:
        surface = "test"

        async def deliver(self, stream, _message):
            async for event in stream:
                yield str(event).encode()

    channel_message = {
        "user_id": _uuid.uuid4(),
        "conversation_id": _uuid.uuid4(),
        "text": "and 3+3?",
        "surface": "test",
        "model_id": "test:fake",
        "metadata": {},
    }

    history_rows = [
        {"role": "user", "content": "what's 2+2?"},
        {"role": "assistant", "content": "4"},
    ]

    async def _persist(_turn_input):
        return history_rows, _uuid.uuid4()

    async def _noop_finalize(**_kwargs):
        return None

    monkeypatch.setattr("app.channels.turn_runner._load_history_and_persist", _persist)
    monkeypatch.setattr("app.channels.turn_runner._finalize_turn", _noop_finalize)

    turn_input = ChatTurnInput(
        conversation_id=channel_message["conversation_id"],
        user_id=channel_message["user_id"],
        question="and 3+3?",
        provider=_FakeProvider(),  # type: ignore[arg-type]
        channel=_FakeChannel(),  # type: ignore[arg-type]
        channel_message=channel_message,  # type: ignore[arg-type]
    )

    async for _chunk in run_turn(turn_input):
        pass

    llm_chat_span = _span_by_name(span_exporter, "pawrrtal.llm.chat")
    payload = json.loads(str(_attrs(llm_chat_span)["gen_ai.input.messages"]))
    assert [m["role"] for m in payload] == ["user", "assistant", "user"]
    assert payload[0]["parts"][0]["content"] == "what's 2+2?"
    assert payload[1]["parts"][0]["content"] == "4"
    assert payload[2]["parts"][0]["content"] == "and 3+3?"


# ---------------------------------------------------------------------------
# Latency: TTFT + duration on LLM and turn spans
# ---------------------------------------------------------------------------


def test_llm_recorder_stamps_duration_and_ttft_after_delta(
    span_exporter: InMemorySpanExporter,
) -> None:
    """A delta-bearing turn stamps both ``pawrrtal.llm.duration_ms`` and ``...ttft_ms``."""
    with llm_span(model_id="m", messages=[], system_prompt=None) as recorder:
        recorder.record_text_delta("hi")
        recorder.record_text_delta("there")

    attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.llm.chat"))
    ttft = attrs.get("pawrrtal.llm.ttft_ms")
    duration = attrs.get("pawrrtal.llm.duration_ms")
    assert isinstance(ttft, (int, float))
    assert isinstance(duration, (int, float))
    # ttft <= duration is the only safe assertion — wall-clock readings
    # otherwise vary too much to pin a numeric bound.
    assert ttft <= duration
    assert duration >= 0.0


def test_llm_recorder_omits_ttft_when_no_delta(
    span_exporter: InMemorySpanExporter,
) -> None:
    """A turn that streams no token stamps duration but not TTFT.

    Protects the invariant that ``pawrrtal.llm.ttft_ms`` only appears
    when an actual first token was observed.  Without it, a provider
    error before any token would show a misleading sub-millisecond TTFT
    in dashboards that just plot the attribute.
    """
    with llm_span(model_id="m", messages=[], system_prompt=None):
        pass

    attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.llm.chat"))
    assert "pawrrtal.llm.duration_ms" in attrs
    assert "pawrrtal.llm.ttft_ms" not in attrs


def test_llm_recorder_ttft_set_on_thinking_delta_first(
    span_exporter: InMemorySpanExporter,
) -> None:
    """Reasoning models that emit ``thinking`` before ``text`` still get TTFT.

    Otherwise a long reasoning preamble (Claude with extended thinking,
    OpenAI o1) would log a TTFT that excludes the visible-but-pre-text
    wait — exactly the latency a user is feeling.
    """
    with llm_span(model_id="m", messages=[], system_prompt=None) as recorder:
        recorder.record_thinking_delta("planning")
        recorder.record_text_delta("answer")

    attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.llm.chat"))
    assert "pawrrtal.llm.ttft_ms" in attrs


def test_turn_recorder_record_first_event_is_idempotent() -> None:
    """Only the first ``record_first_event`` call captures TTFT.

    Direct recorder test — bypasses the OTel span machinery to pin the
    idempotency contract that ``workshop_event_hook`` relies on (it
    calls ``record_first_event`` on every event without tracking
    whether it's already fired).
    """
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("test") as span:
        recorder = TurnSpanRecorder(span)
        assert recorder.ttft_ms is None
        recorder.record_first_event()
        first_value = recorder.ttft_ms
        assert first_value is not None
        # Burning a tiny bit of wall-clock — if the second call wasn't
        # idempotent, this would overwrite ``_ttft_ms`` with a larger
        # number, so equality is a meaningful assertion.
        for _ in range(100):
            recorder.record_first_event()
        assert recorder.ttft_ms == first_value


def test_turn_span_stamps_duration_and_ttft_when_first_event_recorded(
    span_exporter: InMemorySpanExporter,
) -> None:
    """``turn_span`` flushes ``pawrrtal.turn.*`` latency attributes on exit."""
    with turn_span(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        surface="WEB",
        request_id="req-1",
        model_id="m",
    ) as turn_recorder:
        turn_recorder.record_first_event()

    attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.turn"))
    assert "pawrrtal.turn.duration_ms" in attrs
    assert "pawrrtal.turn.ttft_ms" in attrs


def test_turn_span_omits_ttft_when_no_event(span_exporter: InMemorySpanExporter) -> None:
    """A turn that never produced an event stamps duration but not TTFT."""
    with turn_span(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        surface="WEB",
        request_id="req-1",
        model_id="m",
    ):
        pass

    attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.turn"))
    assert "pawrrtal.turn.duration_ms" in attrs
    assert "pawrrtal.turn.ttft_ms" not in attrs


def test_workshop_event_hook_marks_turn_ttft(span_exporter: InMemorySpanExporter) -> None:
    """When provided, ``turn_recorder`` gets pinged by the LLM event hook."""
    with (
        turn_span(
            conversation_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            surface="WEB",
            request_id="req-1",
            model_id="m",
        ) as turn_recorder,
        llm_span(model_id="m", messages=[], system_prompt=None) as llm_recorder,
    ):
        hook = workshop_event_hook(llm_recorder, turn_recorder=turn_recorder)
        assert hook({"type": "delta", "content": "hi"}) == []

    turn_attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.turn"))
    assert "pawrrtal.turn.ttft_ms" in turn_attrs


@pytest.mark.anyio
async def test_run_turn_stamps_latency_attributes_on_turn_span(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``run_turn`` populates both ``pawrrtal.turn.*`` latency attributes.

    Integration check that the hook plumbing in ``_stream_with_llm_span``
    actually wires ``turn_recorder`` through ``workshop_event_hook``.
    Without this, a refactor that drops the kwarg would silently break
    TTFT capture for every chat turn.
    """
    import uuid as _uuid

    from app.channels.turn_runner import ChatTurnInput, run_turn

    class _FakeProvider:
        async def stream(self, *_args: object, **_kwargs: object):
            yield {"type": "delta", "content": "hello"}
            yield {
                "type": "usage",
                "input_tokens": 3,
                "output_tokens": 1,
                "cost_usd": 0.0,
            }

    class _FakeChannel:
        surface = "test"

        async def deliver(self, stream, _message):
            async for event in stream:
                yield str(event).encode()

    channel_message = {
        "user_id": _uuid.uuid4(),
        "conversation_id": _uuid.uuid4(),
        "text": "hi",
        "surface": "test",
        "model_id": "test:fake",
        "metadata": {},
    }

    async def _persist(_turn_input):
        return [], _uuid.uuid4()

    async def _noop_finalize(**_kwargs):
        # Capture the kwargs the runner forwards so the test can also
        # assert that the latency value flows into the log / event
        # plumbing, not only the span.
        _noop_finalize.last_kwargs = _kwargs  # type: ignore[attr-defined]

    monkeypatch.setattr("app.channels.turn_runner._load_history_and_persist", _persist)
    monkeypatch.setattr("app.channels.turn_runner._finalize_turn", _noop_finalize)

    turn_input = ChatTurnInput(
        conversation_id=channel_message["conversation_id"],
        user_id=channel_message["user_id"],
        question="hi",
        provider=_FakeProvider(),  # type: ignore[arg-type]
        channel=_FakeChannel(),  # type: ignore[arg-type]
        channel_message=channel_message,  # type: ignore[arg-type]
    )

    async for _chunk in run_turn(turn_input):
        pass

    turn_attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.turn"))
    assert "pawrrtal.turn.duration_ms" in turn_attrs
    assert "pawrrtal.turn.ttft_ms" in turn_attrs
    forwarded = _noop_finalize.last_kwargs  # type: ignore[attr-defined]
    assert forwarded["ttft_ms"] is not None
    assert forwarded["ttft_ms"] >= 0.0
