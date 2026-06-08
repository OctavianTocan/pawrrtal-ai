"""Run-turn and latency tests for agent trace observability."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any, cast
from uuid import UUID

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.infrastructure.observability import agent_trace as agent_trace_module
from app.infrastructure.observability._recorders import TurnSpanRecorder
from app.infrastructure.observability.agent_trace import (
    agent_event_hook,
    llm_span,
    turn_span,
)


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    previous_provider = trace.get_tracer_provider()
    previous_module_tracer = agent_trace_module._tracer
    trace.set_tracer_provider(provider)
    agent_trace_module._tracer = provider.get_tracer("test")
    try:
        yield exporter
    finally:
        agent_trace_module._tracer = previous_module_tracer
        agent_trace_module._previous_turn.clear()
        trace.set_tracer_provider(previous_provider)
        provider.shutdown()


def _attrs(span: ReadableSpan) -> dict[str, object]:
    return dict(span.attributes or {})


def _span_by_name(exporter: InMemorySpanExporter, name: str) -> ReadableSpan:
    matches = [span for span in exporter.get_finished_spans() if span.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r} span, got {len(matches)}"
    return matches[0]


@pytest.mark.anyio
async def test_finalize_turn_errors_do_not_taint_llm_span(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A finalize failure marks the turn span but not the completed LLM span."""
    from app.channels.turn_orchestrator import ChatTurnInput, run_turn

    class _FakeProvider:
        async def stream(self, *_args: object, **_kwargs: object) -> AsyncIterator[Any]:
            yield {"type": "delta", "content": "hi"}
            yield {"type": "usage", "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0}

    class _FakeChannel:
        surface = "test"

        async def deliver(
            self, stream: AsyncIterator[Any], _message: object
        ) -> AsyncIterator[bytes]:
            async for event in stream:
                yield str(event).encode()

    channel_message = {
        "user_id": uuid.uuid4(),
        "conversation_id": uuid.uuid4(),
        "text": "hello",
        "surface": "test",
        "model_id": "test:fake",
        "metadata": {},
    }

    async def _no_persist(_turn_input: object) -> tuple[list[dict[str, str]], uuid.UUID]:
        return [{"role": "user", "content": "prior"}], uuid.uuid4()

    async def _failing_finalize(**_kwargs: object) -> None:
        raise RuntimeError("simulated DB persist failure")

    monkeypatch.setattr(
        "app.channels.turn_orchestrator.runner._load_history_and_persist",
        _no_persist,
    )
    monkeypatch.setattr(
        "app.channels.turn_orchestrator.runner._finalize_turn",
        _failing_finalize,
    )

    turn_input = ChatTurnInput(
        conversation_id=cast("UUID", channel_message["conversation_id"]),
        user_id=cast("UUID", channel_message["user_id"]),
        question="hello",
        provider=_FakeProvider(),
        channel=_FakeChannel(),
        channel_message=channel_message,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="simulated DB persist failure"):
        async for _chunk in run_turn(turn_input):
            pass

    llm_chat_span = _span_by_name(span_exporter, "pawrrtal.llm.chat")
    assert llm_chat_span.status.status_code != trace.StatusCode.ERROR
    turn_span_recorded = _span_by_name(span_exporter, "pawrrtal.turn")
    assert turn_span_recorded.status.status_code == trace.StatusCode.ERROR


@pytest.mark.anyio
async def test_run_turn_passes_history_into_llm_span(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``gen_ai.input.messages`` carries the full conversation."""
    from app.channels.turn_orchestrator import ChatTurnInput, run_turn

    class _FakeProvider:
        async def stream(self, *_args: object, **_kwargs: object) -> AsyncIterator[Any]:
            yield {"type": "delta", "content": "ack"}

    class _FakeChannel:
        surface = "test"

        async def deliver(
            self, stream: AsyncIterator[Any], _message: object
        ) -> AsyncIterator[bytes]:
            async for event in stream:
                yield str(event).encode()

    channel_message = {
        "user_id": uuid.uuid4(),
        "conversation_id": uuid.uuid4(),
        "text": "and 3+3?",
        "surface": "test",
        "model_id": "test:fake",
        "metadata": {},
    }
    history_rows = [
        {"role": "user", "content": "what's 2+2?"},
        {"role": "assistant", "content": "4"},
    ]

    async def _persist(_turn_input: object) -> tuple[list[dict[str, str]], uuid.UUID]:
        return history_rows, uuid.uuid4()

    async def _noop_finalize(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.channels.turn_orchestrator.runner._load_history_and_persist", _persist)
    monkeypatch.setattr("app.channels.turn_orchestrator.runner._finalize_turn", _noop_finalize)

    turn_input = ChatTurnInput(
        conversation_id=cast("UUID", channel_message["conversation_id"]),
        user_id=cast("UUID", channel_message["user_id"]),
        question="and 3+3?",
        provider=_FakeProvider(),
        channel=_FakeChannel(),
        channel_message=channel_message,  # type: ignore[arg-type]
    )

    async for _chunk in run_turn(turn_input):
        pass

    llm_chat_span = _span_by_name(span_exporter, "pawrrtal.llm.chat")
    payload = json.loads(str(_attrs(llm_chat_span)["gen_ai.input.messages"]))
    assert [message["role"] for message in payload] == ["user", "assistant", "user"]
    assert payload[0]["parts"][0]["content"] == "what's 2+2?"
    assert payload[1]["parts"][0]["content"] == "4"
    assert payload[2]["parts"][0]["content"] == "and 3+3?"


def test_llm_recorder_stamps_duration_and_ttft_after_delta(
    span_exporter: InMemorySpanExporter,
) -> None:
    with llm_span(model_id="m", messages=[], system_prompt=None) as recorder:
        recorder.record_text_delta("hi")
        recorder.record_text_delta("there")

    attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.llm.chat"))
    ttft = attrs.get("pawrrtal.llm.ttft_ms")
    duration = attrs.get("pawrrtal.llm.duration_ms")
    assert isinstance(ttft, (int, float))
    assert isinstance(duration, (int, float))
    assert ttft <= duration
    assert duration >= 0.0


def test_llm_recorder_omits_ttft_when_no_delta(
    span_exporter: InMemorySpanExporter,
) -> None:
    with llm_span(model_id="m", messages=[], system_prompt=None):
        pass

    attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.llm.chat"))
    assert "pawrrtal.llm.duration_ms" in attrs
    assert "pawrrtal.llm.ttft_ms" not in attrs


def test_llm_recorder_ttft_set_on_thinking_delta_first(
    span_exporter: InMemorySpanExporter,
) -> None:
    with llm_span(model_id="m", messages=[], system_prompt=None) as recorder:
        recorder.record_thinking_delta("planning")
        recorder.record_text_delta("answer")

    attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.llm.chat"))
    assert "pawrrtal.llm.ttft_ms" in attrs


def test_turn_recorder_record_first_event_is_idempotent() -> None:
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("test") as span:
        recorder = TurnSpanRecorder(span)
        assert recorder.ttft_ms is None
        recorder.record_first_event()
        first_value = recorder.ttft_ms
        assert first_value is not None
        for _ in range(100):
            recorder.record_first_event()
        assert recorder.ttft_ms == first_value


def test_turn_span_stamps_duration_and_ttft_when_first_event_recorded(
    span_exporter: InMemorySpanExporter,
) -> None:
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


def test_agent_event_hook_marks_turn_ttft(span_exporter: InMemorySpanExporter) -> None:
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
        hook = agent_event_hook(llm_recorder, turn_recorder=turn_recorder)
        assert hook({"type": "delta", "content": "hi"}) == []

    turn_attrs = _attrs(_span_by_name(span_exporter, "pawrrtal.turn"))
    assert "pawrrtal.turn.ttft_ms" in turn_attrs


@pytest.mark.anyio
async def test_run_turn_stamps_latency_attributes_on_turn_span(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.channels.turn_orchestrator import ChatTurnInput, run_turn

    class _FakeProvider:
        async def stream(self, *_args: object, **_kwargs: object) -> AsyncIterator[Any]:
            yield {"type": "delta", "content": "hello"}
            yield {"type": "usage", "input_tokens": 3, "output_tokens": 1, "cost_usd": 0.0}

    class _FakeChannel:
        surface = "test"

        async def deliver(
            self, stream: AsyncIterator[Any], _message: object
        ) -> AsyncIterator[bytes]:
            async for event in stream:
                yield str(event).encode()

    channel_message = {
        "user_id": uuid.uuid4(),
        "conversation_id": uuid.uuid4(),
        "text": "hi",
        "surface": "test",
        "model_id": "test:fake",
        "metadata": {},
    }

    async def _persist(_turn_input: object) -> tuple[list[dict[str, str]], uuid.UUID]:
        return [], uuid.uuid4()

    async def _noop_finalize(**_kwargs: object) -> None:
        _noop_finalize.last_kwargs = _kwargs  # type: ignore[attr-defined]

    monkeypatch.setattr("app.channels.turn_orchestrator.runner._load_history_and_persist", _persist)
    monkeypatch.setattr("app.channels.turn_orchestrator.runner._finalize_turn", _noop_finalize)

    turn_input = ChatTurnInput(
        conversation_id=cast("UUID", channel_message["conversation_id"]),
        user_id=cast("UUID", channel_message["user_id"]),
        question="hi",
        provider=_FakeProvider(),
        channel=_FakeChannel(),
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


def test_turn_span_links_to_previous_turn_in_same_conversation(
    span_exporter: InMemorySpanExporter,
) -> None:
    conv_id = uuid.uuid4()

    with turn_span(
        conversation_id=conv_id,
        user_id=uuid.uuid4(),
        surface="WEB",
        request_id="r1",
        model_id="test:model",
    ):
        pass
    first_turn = span_exporter.get_finished_spans()[-1]
    assert first_turn.links is None or len(first_turn.links) == 0
    span_exporter.clear()

    with turn_span(
        conversation_id=conv_id,
        user_id=uuid.uuid4(),
        surface="WEB",
        request_id="r2",
        model_id="test:model",
    ):
        pass
    second_turn = span_exporter.get_finished_spans()[-1]
    assert second_turn.links is not None
    assert len(second_turn.links) == 1
    assert second_turn.links[0].context.span_id == first_turn.context.span_id
    assert second_turn.links[0].context.trace_id == first_turn.context.trace_id


def test_turn_span_no_link_across_different_conversations(
    span_exporter: InMemorySpanExporter,
) -> None:
    with turn_span(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        surface="WEB",
        request_id="r1",
        model_id="test:model",
    ):
        pass
    span_exporter.clear()

    with turn_span(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        surface="WEB",
        request_id="r2",
        model_id="test:model",
    ):
        pass
    second_turn = span_exporter.get_finished_spans()[-1]
    assert second_turn.links is None or len(second_turn.links) == 0
