"""Bridging helpers between Pawrrtal turn state and the agent trace span shape.

Pulled out of ``app.turns.pipeline`` so that module stays under
the project's 500-line ceiling (``scripts/check-file-lines.mjs``) and
the agent-trace translations live next to the rest of the
observability package.

Both helpers are private to ``app.infrastructure.observability`` /
``app.turns.pipeline``; the public surface remains the context
managers exposed via ``app.infrastructure.observability.agent_trace``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.types import AgentMessage
    from app.chat.aggregator import ChatTurnAggregator


def build_llm_view_messages(
    history: list[dict[str, str]],
    current_question: str,
) -> list[AgentMessage]:
    """Render ``history + current_question`` as ``AgentMessage`` for the LLM span.

    The chat-message table stores both user and assistant turns as
    flat ``{"role": ..., "content": str}`` rows so
    ``_load_history_and_persist`` can hand them to the provider
    unchanged. Trace viewers that render ``gen_ai.input.messages`` expect the
    canonical ``AgentMessage`` union, so we lift each row into the
    matching TypedDict here.

    Assistant rows from the chat-message table are stored as a single
    text string (the visible message body); they lose any historical
    tool-call structure once persisted.  We render them with a single
    ``TextContent`` block and a synthetic ``stop_reason='stop'`` so
    the shape is valid even though no tool history is recoverable.
    Rows with unknown roles (e.g. ``"system"``, ``"tool"``) are
    skipped silently — observability must never crash a chat turn if
    the message table gains a new role.
    """
    rendered: list[AgentMessage] = []
    for row in history:
        role = row.get("role")
        content = row.get("content", "")
        if role == "user":
            rendered.append({"role": "user", "content": content})
        elif role == "assistant":
            rendered.append(
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": content}],
                    "stop_reason": "stop",
                }
            )
    rendered.append({"role": "user", "content": current_question})
    return rendered


def aggregator_stop_reason(aggregator: ChatTurnAggregator) -> str:
    """Best-effort ``stop_reason`` for the trace viewer LLM span.

    The :class:`ChatTurnAggregator` does not track the provider's
    literal ``stop_reason`` — it normalises the wire shape to
    ``status`` (``complete`` / ``failed``) at finalisation time.  For
    trace viewer's ``gen_ai.response.finish_reasons`` attribute we infer:

    * ``"error"`` when the aggregator captured an error event,
    * ``"tool_use"`` when at least one tool call was dispatched,
    * ``"stop"`` otherwise (the normal text-only finish).

    This matches the three values the agent loop's ``stop_reason``
    enum can take, so the trace UI shows the same labels operators
    see in the backend logs.
    """
    if aggregator.error_text:
        return "error"
    if aggregator.tool_calls:
        return "tool_use"
    return "stop"
