"""Tests for the test-injectable tracer in workshop (#352 L6)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.observability.workshop import (
    reset_tracer_for_tests,
    set_tracer_for_tests,
    turn_span,
)


@pytest.fixture
def in_memory_tracer() -> Iterator[tuple[trace.Tracer, InMemorySpanExporter]]:
    """Per-test tracer + exporter so spans don't bleed across tests.

    Returns the tracer (for ``set_tracer_for_tests``) and the
    exporter (for reading recorded spans). The tracer provider is
    discarded after the test — never installed globally — which is
    exactly the property #352 L6 was designed to give us.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("pawrrtal-tests")
    set_tracer_for_tests(tracer)
    try:
        yield tracer, exporter
    finally:
        reset_tracer_for_tests()
        provider.shutdown()


def test_turn_span_emits_through_injected_tracer(
    in_memory_tracer: tuple[trace.Tracer, InMemorySpanExporter],
) -> None:
    """A turn_span recorded via the injected tracer lands in the exporter.

    The matching production span (without the override) would land
    on the configured OTLP collector. Reading back the
    in-memory-exported span confirms ``_active_tracer()`` is the
    seam the override flows through.
    """
    _, exporter = in_memory_tracer

    with turn_span(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        surface="telegram",
        request_id="req-1",
        model_id="agent-sdk:anthropic/claude-sonnet-4-6",
    ):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "pawrrtal.turn"
    assert span.attributes.get("pawrrtal.surface") == "telegram"


def test_reset_tracer_for_tests_restores_module_default(
    in_memory_tracer: tuple[trace.Tracer, InMemorySpanExporter],
) -> None:
    """After ``reset_tracer_for_tests``, the module tracer takes over again.

    Without this guarantee, an override from a forgotten ``finally``
    block in one test would pollute every subsequent test in the
    suite. The fixture's ``finally`` exercises the reset path; the
    assertion below confirms a second turn_span doesn't end up in
    the test exporter.
    """
    _, exporter = in_memory_tracer

    # Reset BEFORE the second span — this is the same code the
    # fixture runs in its teardown; here we run it inline so the
    # assertion isn't a tautology over the fixture's teardown.
    reset_tracer_for_tests()

    with turn_span(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        surface="web",
        request_id="req-2",
        model_id=None,
    ):
        pass

    # The exporter should NOT have recorded this span — after
    # reset the module tracer (the no-op tracer in test envs
    # without OTel configured) takes over.
    assert not exporter.get_finished_spans()
