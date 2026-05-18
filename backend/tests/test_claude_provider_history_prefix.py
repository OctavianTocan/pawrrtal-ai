"""Tests for Claude provider's history-prefix fallback (#308).

When a user switches providers mid-conversation, the Claude SDK does
not have its own transcript for the conversation. The provider should
prepend a bounded summary of the app-level history so the model sees
the prior turns.
"""

from __future__ import annotations

from app.core.providers.claude_provider import _render_history_prefix


def test_returns_none_for_empty_history() -> None:
    assert _render_history_prefix(None) is None
    assert _render_history_prefix([]) is None


def test_returns_none_for_history_with_only_blank_rows() -> None:
    result = _render_history_prefix(
        [
            {"role": "user", "content": "   "},
            {"role": "assistant", "content": ""},
        ]
    )
    assert result is None


def test_wraps_history_with_markers() -> None:
    history = [
        {"role": "user", "content": "Hello Gemini"},
        {"role": "assistant", "content": "Hi there"},
    ]
    result = _render_history_prefix(history)
    assert result is not None
    assert "BEGIN PRIOR CONTEXT" in result
    assert "END PRIOR CONTEXT" in result
    assert "User: Hello Gemini" in result
    assert "Assistant: Hi there" in result


def test_drops_tool_or_system_rows() -> None:
    history = [
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "ignored too"},
        {"role": "assistant", "content": "hey"},
    ]
    result = _render_history_prefix(history)
    assert result is not None
    assert "ignored" not in result
    assert "User: hi" in result
    assert "Assistant: hey" in result


def test_truncates_giant_history_keeping_tail() -> None:
    history = [{"role": "user", "content": f"turn {i}: " + "x" * 500} for i in range(200)]
    result = _render_history_prefix(history)
    assert result is not None
    # Tail must include the most-recent row.
    assert "turn 199" in result
    # Body must be bounded.
    assert len(result) < 20_000
