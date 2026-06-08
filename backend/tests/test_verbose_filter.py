"""Tests for ``app.chat.aggregator.should_emit_event``.

Covers the three CCT-style verbose levels (0/1/2) and confirms the
right event types survive each level.
"""

from __future__ import annotations

import pytest

from app.chat.aggregator import (
    VERBOSE_DETAILED,
    VERBOSE_NORMAL,
    VERBOSE_QUIET,
    should_emit_event,
)
from app.providers.base import StreamEvent
from app.turns.pipeline import _should_deliver_event


def _ev(t: str, **kw: object) -> StreamEvent:
    payload: StreamEvent = {"type": t}
    for k, v in kw.items():
        payload[k] = v  # type: ignore[literal-required]
    return payload


class TestQuiet:
    """Level 0 — only deltas + errors + usage survive."""

    @pytest.mark.parametrize(
        "ev",
        [_ev("delta", content="x"), _ev("error", content="boom"), _ev("usage")],
    )
    def test_kept(self, ev: StreamEvent) -> None:
        assert should_emit_event(ev, VERBOSE_QUIET) is True

    @pytest.mark.parametrize(
        "ev",
        [
            _ev("thinking", content="thoughts"),
            _ev("tool_use", name="t"),
            _ev("tool_result", tool_use_id="x", content="r"),
            _ev("artifact"),
        ],
    )
    def test_dropped(self, ev: StreamEvent) -> None:
        assert should_emit_event(ev, VERBOSE_QUIET) is False


class TestNormal:
    """Level 1 — adds tool calls, artifacts, and safe thinking summaries."""

    @pytest.mark.parametrize(
        "ev",
        [
            _ev("delta", content="x"),
            _ev("tool_use", name="workspace_read"),
            _ev("tool_result", tool_use_id="x", content="r"),
            _ev("artifact"),
            _ev("error", content="boom"),
            _ev("usage"),
        ],
    )
    def test_kept(self, ev: StreamEvent) -> None:
        assert should_emit_event(ev, VERBOSE_NORMAL) is True

    def test_thinking_dropped(self) -> None:
        assert should_emit_event(_ev("thinking", content="thoughts"), VERBOSE_NORMAL) is False

    def test_summary_thinking_kept(self) -> None:
        assert (
            should_emit_event(
                _ev("thinking", content="safe summary", summary=True),
                VERBOSE_NORMAL,
            )
            is True
        )


class TestDetailed:
    """Level 2 — everything passes through, including thinking."""

    @pytest.mark.parametrize(
        "ev",
        [
            _ev("delta", content="x"),
            _ev("thinking", content="thoughts"),
            _ev("tool_use", name="workspace_read"),
            _ev("tool_result", tool_use_id="x", content="r"),
            _ev("artifact"),
            _ev("error", content="boom"),
            _ev("usage"),
        ],
    )
    def test_kept(self, ev: StreamEvent) -> None:
        assert should_emit_event(ev, VERBOSE_DETAILED) is True


class TestTurnRunnerVerboseBridge:
    """ChatTurnInput.verbose_level is the seam that applies the filter."""

    def test_none_keeps_everything_for_web_chat(self) -> None:
        assert _should_deliver_event(_ev("thinking", content="thoughts"), None) is True

    def test_quiet_drops_tool_events_for_telegram(self) -> None:
        assert _should_deliver_event(_ev("tool_use", name="workspace_read"), VERBOSE_QUIET) is False

    def test_detailed_keeps_thinking_for_telegram(self) -> None:
        assert _should_deliver_event(_ev("thinking", content="thoughts"), VERBOSE_DETAILED) is True
