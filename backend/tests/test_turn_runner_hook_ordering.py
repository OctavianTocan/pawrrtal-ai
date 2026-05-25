"""Hook-ordering tests for ``_guarded_stream`` (#347 / #352 L3).

The verbose filter is a channel rendering concern; observability hooks
(Workshop / OTel span recorders) must see every event regardless of
``verbose_level``. The previous implementation ran the filter first,
short-circuiting before the hook fan-out — so thinking deltas at
``verbose_level=1`` (Telegram's default) were invisible to the LLM
span.

These tests pin the new order at the unit seam (``_guarded_stream``)
so the regression can't ship silently again.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.channels.turn_runner import ChatTurnInput, _guarded_stream
from app.core.chat_aggregator import ChatTurnAggregator
from app.core.providers.base import StreamEvent


class _ScriptedProvider:
    """Minimal ``AILLM`` stand-in that yields a hard-coded event sequence."""

    def __init__(self, events: list[StreamEvent]) -> None:
        self._events = events

    def stream(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[StreamEvent]:
        for event in self._events:
            yield event


def _make_turn_input(provider: _ScriptedProvider, *, verbose_level: int) -> ChatTurnInput:
    """Build a ``ChatTurnInput`` with the minimum surface ``_guarded_stream`` reads."""
    # ``_guarded_stream`` only touches a narrow subset of the dataclass
    # (provider, question, IDs, tools, verbose_level); other fields are
    # stubs that satisfy the dataclass without exercising real types.
    return ChatTurnInput(
        conversation_id=MagicMock(),
        user_id=MagicMock(),
        question="hi",
        provider=provider,  # type: ignore[arg-type]
        channel=MagicMock(),
        channel_message=MagicMock(),
        workspace_root=None,
        tools=[],
        images=None,
        permission_check=None,
        log_tag="TEST",
        log_extras={},
        verbose_level=verbose_level,
        reasoning_effort=None,
    )


class _Counter:
    """Stand-in for the private ``_EventCounter`` used by ``_guarded_stream``."""

    def __init__(self) -> None:
        self.value = 0
        self.by_type: dict[str, int] = {}

    def record(self, event: StreamEvent) -> None:
        self.value += 1
        etype = event.get("type", "")
        self.by_type[etype] = self.by_type.get(etype, 0) + 1


@pytest.mark.anyio
async def test_hooks_observe_thinking_at_verbose_normal() -> None:
    """Verbose=1 hides thinking from the channel but hooks still see it (#347).

    With ``verbose_level=1`` (Telegram's default) the filter drops
    ``thinking`` events before they reach the channel — but the
    Workshop hook lives in the same ``hooks`` list and must observe
    every event so the LLM span gets ``gen_ai.thinking.delta`` entries.
    """
    seen_events: list[StreamEvent] = []

    def recording_hook(event: StreamEvent) -> list[StreamEvent]:
        seen_events.append(event)
        return []

    provider = _ScriptedProvider(
        [
            {"type": "thinking", "content": "let me think..."},
            {"type": "delta", "content": "Hello."},
        ]
    )
    turn_input = _make_turn_input(provider, verbose_level=1)
    aggregator = ChatTurnAggregator()
    counter = _Counter()

    delivered = [
        e
        async for e in _guarded_stream(
            turn_input=turn_input,
            history=[],
            system_prompt=None,
            aggregator=aggregator,
            counter=counter,  # type: ignore[arg-type]
            hooks=[recording_hook],
        )
    ]

    # The hook observed BOTH events, even though only the delta was delivered.
    assert any(e.get("type") == "thinking" for e in seen_events)
    assert any(e.get("type") == "delta" for e in seen_events)
    # The channel saw only the delta — the filter still gates rendering.
    assert [e.get("type") for e in delivered] == ["delta"]
