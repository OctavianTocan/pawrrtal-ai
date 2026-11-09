"""Chat round-trip verification scenario.

Question this scenario answers: "If the SSE stream looked right but the
``chat_messages`` row is wrong, does this suite catch it?"

The scenario drives one chat turn with ``reasoning_effort="high"``,
records every SSE event the backend emits, then fetches the persisted
``chat_messages`` rows and asserts the stream ↔ DB invariants:

- The stored assistant ``content`` is a heuristic substring match of the
  text assembled from the stream's ``delta`` / ``message`` events.
- ``tool_calls`` row count equals the number of ``tool_use`` events seen.
- Stored ``thinking`` matches the concatenated ``thinking`` events when
  any arrived; ``thinking_duration_seconds > 0`` in the same case.
- ``assistant_status == "complete"`` after the stream terminates.

The intent is to catch the entire bug class the chat router has shipped
historically — block_index drops, thinking rendering, telegram chunk
dropouts — by comparing the live wire shape against the rehydrated row.
"""

from __future__ import annotations

from typing import Any

from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify import helpers
from app.cli.paw.verify.scenarios import ScenarioResult

TURN_TEXT = "Say hello briefly."
SCENARIO_TITLE = "paw verify chat-roundtrip"
REASONING_EFFORT = "high"


def _assemble_final_text(events: list[dict[str, Any]]) -> str:
    """Concatenate text-bearing events the way the frontend renderer does."""
    parts: list[str] = []
    for e in events:
        if e.get("type") in ("delta", "message"):
            content = e.get("content")
            if isinstance(content, str):
                parts.append(content)
    return "".join(parts)


def _assemble_thinking(events: list[dict[str, Any]]) -> str:
    """Concatenate ``thinking`` events into one string for DB comparison."""
    parts: list[str] = []
    for e in events:
        if e.get("type") == "thinking":
            content = e.get("content")
            if isinstance(content, str):
                parts.append(content)
    return "".join(parts)


def _content_matches(stream_text: str, stored: str) -> bool:
    """Heuristic match between streamed final text and persisted content.

    We don't require byte equality because the backend normalises
    trailing whitespace and may collapse adjacent newlines on persist.
    We accept either substring direction: the stored content may be a
    prefix of the stream (stream has trailing tool-result text) or
    the stream may be a prefix of the stored row (stored row includes
    artifact synthesis appended after the last delta).
    """
    a = stream_text.strip()
    b = stored.strip()
    if not a or not b:
        return a == b
    return a in b or b in a


def _assert_stream_shape(r: ScenarioResult, events: list[dict[str, Any]]) -> None:
    """Stream-side assertions before comparing to DB."""
    errors = [e for e in events if e.get("type") == "error"]
    done = any(e.get("type") == "done" for e in events)
    text_events = [e for e in events if e.get("type") in ("delta", "message")]
    r.add("stream_no_errors", len(errors) == 0, detail=f"first={errors[0] if errors else None}")
    r.add("stream_terminates_with_done", done)
    r.add("stream_has_text_events", len(text_events) > 0, detail=f"events={len(text_events)}")


def _find_assistant(msgs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the last assistant row in the message list, or ``None``."""
    for row in reversed(msgs):
        if isinstance(row, dict) and row.get("role") == "assistant":
            return row
    return None


def _assert_stream_vs_db(
    r: ScenarioResult,
    events: list[dict[str, Any]],
    msgs: list[dict[str, Any]],
) -> None:
    """The headline comparison: stream events vs persisted chat_messages row."""
    assistant = _find_assistant(msgs)
    if assistant is None:
        r.add("assistant_row_present", False, detail="no assistant row in /messages")
        return
    r.add("assistant_row_present", True)

    stream_text = _assemble_final_text(events)
    stored_content = assistant.get("content") or ""
    r.add(
        "content_matches_stream",
        _content_matches(stream_text, stored_content),
        detail=f"stream={stream_text[:60]!r} stored={stored_content[:60]!r}",
    )

    tool_use_count = sum(1 for e in events if e.get("type") == "tool_use")
    stored_calls = assistant.get("tool_calls") or []
    stored_call_count = len(stored_calls) if isinstance(stored_calls, list) else 0
    r.add(
        "tool_call_count_matches_stream",
        stored_call_count == tool_use_count,
        detail=f"stream={tool_use_count} stored={stored_call_count}",
    )

    streamed_thinking = _assemble_thinking(events)
    if streamed_thinking:
        stored_thinking = assistant.get("thinking") or ""
        r.add(
            "thinking_matches_stream",
            _content_matches(streamed_thinking, stored_thinking),
            detail=f"stream_len={len(streamed_thinking)} stored_len={len(stored_thinking)}",
        )
        duration = assistant.get("thinking_duration_seconds")
        r.add(
            "thinking_duration_positive",
            isinstance(duration, int) and duration > 0,
            detail=f"duration={duration}",
        )

    r.add(
        "assistant_status_complete",
        assistant.get("assistant_status") == "complete",
        detail=f"status={assistant.get('assistant_status')}",
    )


async def run_chat_roundtrip_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    model_override: str | None = None,
) -> ScenarioResult:
    """Send one ``reasoning_effort=high`` turn and compare stream to DB.

    The scenario is single-turn on purpose — every check is about the
    round-trip integrity of one message pair, not multi-turn state.
    """
    r = ScenarioResult(name="chat-roundtrip")

    model_id = await helpers.resolve_model(client, r, model_override)
    if model_id is None:
        return r

    conv_id = await helpers.create_conversation(client, r, title=SCENARIO_TITLE)
    events = await helpers.stream_turn(
        client,
        conv_id,
        TURN_TEXT,
        model_id=model_id,
        reasoning_effort=REASONING_EFFORT,
    )
    r.artifacts["stream_events"] = events
    _assert_stream_shape(r, events)

    msgs = (await client.request("GET", f"/api/v1/conversations/{conv_id}/messages")).json()
    r.artifacts["messages"] = msgs if isinstance(msgs, list) else None
    if not isinstance(msgs, list):
        r.add("messages_endpoint_returns_list", False, detail=f"got {type(msgs).__name__}")
        await helpers.cleanup_conversation(client, r, conv_id)
        return r
    r.add("messages_endpoint_returns_list", True)
    _assert_stream_vs_db(r, events, msgs)

    await helpers.cleanup_conversation(client, r, conv_id)
    return r
