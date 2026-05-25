"""Tests for the dreaming output schema + parser (#341)."""

from __future__ import annotations

from app.core.dreaming import parse_dreaming_output


def test_parse_clean_json_returns_populated_output() -> None:
    """The happy path: model returns clean JSON, parser populates every field."""
    raw = (
        '{"consolidated_memories": [{"kind": "feedback", "text": "user prefers concise"}],'
        ' "patterns": [{"text": "edits code before running"}],'
        ' "followups": [{"text": "write tests for X", "priority": "high"}],'
        ' "session_summary": "User shipped feature Y today."}'
    )
    out = parse_dreaming_output(raw)
    assert len(out.consolidated_memories) == 1
    assert out.consolidated_memories[0].kind == "feedback"
    assert len(out.patterns) == 1
    assert out.followups[0].priority == "high"
    assert "feature Y" in out.session_summary


def test_parse_strips_markdown_json_fence() -> None:
    """Reasoning models often wrap JSON in a ```json fence — parser tolerates it."""
    raw = (
        "Sure, here's the reflection:\n"
        "```json\n"
        '{"consolidated_memories": [], "patterns": [], "followups": [], '
        '"session_summary": "Quiet session."}\n'
        "```"
    )
    out = parse_dreaming_output(raw)
    assert out.session_summary == "Quiet session."
    assert out.consolidated_memories == []


def test_parse_handles_leading_prose_without_fence() -> None:
    """A reasoning model that ignores the no-prose instruction still parses.

    The parser falls back to "first '{' to last '}'" extraction
    so a 'Here you go:' preface doesn't break the pipeline.
    """
    raw = (
        "Here is what I noticed:\n"
        '{"consolidated_memories": [{"kind": "user", "text": "user is in Madrid"}], '
        '"patterns": [], "followups": [], "session_summary": ""}'
    )
    out = parse_dreaming_output(raw)
    assert out.consolidated_memories[0].text == "user is in Madrid"


def test_parse_returns_empty_output_on_invalid_json() -> None:
    """A model that returns garbage doesn't crash the runner.

    The runner records the failure on ``DreamingJob.error_text``
    and the pass logs at WARNING — the cron keeps running.
    """
    out = parse_dreaming_output("not json at all { broken")
    assert out.consolidated_memories == []
    assert out.session_summary == ""


def test_parse_rejects_unknown_kind() -> None:
    """An invalid ``kind`` value drops the entire output (schema validation)."""
    raw = '{"consolidated_memories": [{"kind": "not-a-kind", "text": "x"}]}'
    out = parse_dreaming_output(raw)
    # Validation failure -> empty output (the runner records the
    # failure but doesn't write half-broken rows).
    assert out.consolidated_memories == []


def test_parse_handles_missing_fields_gracefully() -> None:
    """Partial output is fine — empty defaults for absent fields."""
    raw = '{"consolidated_memories": [{"kind": "user", "text": "owns a Mac"}]}'
    out = parse_dreaming_output(raw)
    assert out.consolidated_memories[0].text == "owns a Mac"
    assert out.patterns == []
    assert out.followups == []
    assert out.session_summary == ""


def test_parse_empty_string_returns_empty_output() -> None:
    """An empty model response shouldn't blow up."""
    out = parse_dreaming_output("")
    assert out.consolidated_memories == []
    assert out.session_summary == ""
