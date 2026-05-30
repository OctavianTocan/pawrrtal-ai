"""Observability helpers — agent-loop and tool spans for OTel collectors.

The ``workshop`` submodule emits OpenLLMetry / Traceloop-flavoured spans
that the local `Raindrop Workshop`_ daemon at ``http://localhost:5899``
renders live (tokens, tool calls, turn boundaries).  The same spans are
valid OTel and route to any standard backend (Grafana, Honeycomb,
SigNoz, Tempo, etc.) — Workshop is just the local renderer.

.. _Raindrop Workshop: https://github.com/raindrop-ai/workshop
"""

from app.infrastructure.observability._turn_view import (
    aggregator_stop_reason,
    build_llm_view_messages,
)
from app.infrastructure.observability.workshop import (
    LLMSpanRecorder,
    ToolSpanRecorder,
    TurnSpanRecorder,
    llm_span,
    tool_span,
    turn_span,
    workshop_event_hook,
)

__all__ = [
    "LLMSpanRecorder",
    "ToolSpanRecorder",
    "TurnSpanRecorder",
    "aggregator_stop_reason",
    "build_llm_view_messages",
    "llm_span",
    "tool_span",
    "turn_span",
    "workshop_event_hook",
]
