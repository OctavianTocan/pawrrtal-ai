"""Tests for OpenAI Codex tool-event shaping."""

from __future__ import annotations

from app.providers.openai_codex.tool_events import truncate_tool_output


def test_truncate_tool_output_does_not_emit_omitted_marker() -> None:
    result = truncate_tool_output("x" * 900, max_chars=100)
    assert len(result) == 100
    assert "more omitted" not in result
    assert "omitted" not in result
