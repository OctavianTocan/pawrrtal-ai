"""Unit tests for the server-side chat-turn aggregator.

Mirrors the frontend `chat-reducer.test.ts` so live and rehydrated views
end up with identical shapes.
"""

from app.chat.aggregator import ChatTurnAggregator


def test_delta_events_concatenate_into_content() -> None:
    """Delta chunks append to `content` and stamp the start timestamp."""
    agg = ChatTurnAggregator()
    agg.apply({"type": "delta", "content": "Hel"})
    agg.apply({"type": "delta", "content": "lo"})

    assert agg.content == "Hello"
    assert agg.started_at_monotonic is not None


def test_consecutive_thinking_events_coalesce_in_timeline() -> None:
    """Two thinking events back-to-back share a single timeline entry."""
    agg = ChatTurnAggregator()
    agg.apply({"type": "thinking", "content": "Let me "})
    agg.apply({"type": "thinking", "content": "think..."})

    assert agg.thinking == "Let me think..."
    assert agg.timeline == [{"kind": "thinking", "text": "Let me think..."}]


def test_fast_thinking_persists_positive_duration() -> None:
    """A fast thinking-only block still rehydrates with a positive duration."""
    agg = ChatTurnAggregator()
    agg.apply({"type": "thinking", "content": "I have a plan."})

    snapshot = agg.to_persisted_shape(status="complete")

    assert snapshot["thinking_duration_seconds"] == 1


def test_tool_break_starts_new_thinking_entry() -> None:
    """A tool_use between thinking events breaks the merge."""
    agg = ChatTurnAggregator()
    agg.apply({"type": "thinking", "content": "A"})
    agg.apply(
        {
            "type": "tool_use",
            "tool_use_id": "t1",
            "name": "web_search",
            "input": {"q": "x"},
            "display": {"present": "Searching the web for x"},
        }
    )
    agg.apply({"type": "thinking", "content": "B"})

    assert agg.timeline == [
        {"kind": "thinking", "text": "A"},
        {"kind": "tool", "toolCallId": "t1"},
        {"kind": "thinking", "text": "B"},
    ]


def test_tool_result_completes_matching_call() -> None:
    """A tool_result flips the matching tool_call to completed and stores result."""
    agg = ChatTurnAggregator()
    agg.apply(
        {
            "type": "tool_use",
            "tool_use_id": "t1",
            "name": "web_search",
            "input": {"q": "x"},
            "display": {"present": "Searching the web for x"},
        }
    )
    agg.apply({"type": "tool_result", "tool_use_id": "t1", "content": "[]"})

    assert agg.tool_calls[0].status == "completed"
    assert agg.tool_calls[0].result == "[]"
    assert agg.tool_calls[0].display == {"present": "Searching the web for x"}


def test_tool_progress_updates_matching_call_without_completing() -> None:
    """A tool_progress event stores preview output but keeps the call pending."""
    agg = ChatTurnAggregator()
    agg.apply(
        {
            "type": "tool_use",
            "tool_use_id": "t1",
            "name": "codex_command",
            "input": {"command": "pytest"},
        }
    )
    agg.apply({"type": "tool_progress", "tool_use_id": "t1", "content": "collected 12 items"})

    assert agg.tool_calls[0].status == "pending"
    assert agg.tool_calls[0].result == "collected 12 items"


def test_persisted_shape_failed_with_no_content_uses_error_text() -> None:
    """Failed turns with no streamed content render the error verbatim."""
    agg = ChatTurnAggregator()
    agg.apply({"type": "error", "content": "rate limited"})

    snapshot = agg.to_persisted_shape(status="failed")
    assert snapshot["assistant_status"] == "failed"
    assert snapshot["content"] == "Error: rate limited"


def test_persisted_shape_complete_keeps_streamed_content() -> None:
    """Successful turns just project content/thinking/tools verbatim."""
    agg = ChatTurnAggregator()
    agg.apply({"type": "delta", "content": "All done."})
    agg.apply({"type": "thinking", "content": "Let me check."})
    agg.apply(
        {
            "type": "tool_use",
            "tool_use_id": "t1",
            "name": "web_search",
            "input": {},
            "display": {"compact": "Search web"},
        }
    )
    agg.apply({"type": "tool_result", "tool_use_id": "t1", "content": "ok"})

    snapshot = agg.to_persisted_shape(status="complete")
    assert snapshot["content"] == "All done."
    assert snapshot["thinking"] == "Let me check."
    assert snapshot["assistant_status"] == "complete"
    assert snapshot["tool_calls"] is not None
    assert snapshot["tool_calls"][0]["status"] == "completed"
    assert snapshot["tool_calls"][0]["display"] == {"compact": "Search web"}
    assert snapshot["timeline"] is not None
