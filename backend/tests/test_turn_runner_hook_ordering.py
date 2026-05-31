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

from app.channels.base import ChannelMessage
from app.channels.turn_runner import ChatTurnInput, _guarded_stream, run_turn
from app.chat.aggregator import ChatTurnAggregator
from app.providers.base import StreamEvent


class _ScriptedProvider:
    """Minimal ``AILLM`` stand-in that yields a hard-coded event sequence."""

    def __init__(self, events: list[StreamEvent]) -> None:
        self._events = events
        self.stream_kwargs: dict[str, Any] = {}

    def stream(
        self,
        *_args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        self.stream_kwargs = kwargs
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
        provider=provider,
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


def _make_codex_turn_input(provider: _ScriptedProvider) -> ChatTurnInput:
    """Build a turn input that simulates a native resumed Codex thread."""
    turn_input = _make_turn_input(provider, verbose_level=2)
    return ChatTurnInput(
        **{
            **turn_input.__dict__,
            "codex_thread_id": "thr_existing",
            "codex_thread_prompt_hash": "hash",
        }
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


class _PassthroughChannel:
    """Minimal channel that drains stream events and emits bytes."""

    surface = "test"

    async def deliver(
        self,
        stream: AsyncIterator[StreamEvent],
        _message: ChannelMessage,
    ) -> AsyncIterator[bytes]:
        async for event in stream:
            yield str(event).encode()


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
            per_turn_context=None,
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


@pytest.mark.anyio
async def test_resumed_codex_thread_does_not_replay_pawrrtal_history() -> None:
    """Native Codex threads own continuity, so app history must not be replayed."""
    provider = _ScriptedProvider([{"type": "delta", "content": "ok"}])
    turn_input = _make_codex_turn_input(provider)
    aggregator = ChatTurnAggregator()
    counter = _Counter()
    history = [{"role": "user", "content": "old"}]

    delivered = [
        e
        async for e in _guarded_stream(
            turn_input=turn_input,
            history=history,
            system_prompt=None,
            per_turn_context="# PRE-TURN CONTEXT\n\nmemory",
            aggregator=aggregator,
            counter=counter,  # type: ignore[arg-type]
            hooks=[],
        )
    ]

    assert delivered == [{"type": "delta", "content": "ok"}]
    assert provider.stream_kwargs["history"] == []
    assert provider.stream_kwargs["codex_thread_id"] == "thr_existing"
    assert provider.stream_kwargs["per_turn_context"] == "# PRE-TURN CONTEXT\n\nmemory"


@pytest.mark.anyio
async def test_transient_progress_is_delivered_but_not_persisted() -> None:
    """Transient progress is UI chrome, not assistant thinking history."""
    provider = _ScriptedProvider(
        [
            {
                "type": "thinking",
                "content": "Preparing the Codex session",
                "summary": True,
                "transient": True,
            },
            {"type": "delta", "content": "ok"},
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
            per_turn_context=None,
            aggregator=aggregator,
            counter=counter,  # type: ignore[arg-type]
            hooks=[],
        )
    ]

    assert [e.get("content") for e in delivered] == ["Preparing the Codex session", "ok"]
    assert aggregator.thinking == ""
    assert aggregator.content == "ok"
    assert counter.by_type == {"delta": 1}


@pytest.mark.anyio
async def test_non_codex_turn_replays_pawrrtal_history() -> None:
    """Non-native providers still receive app-side history."""
    provider = _ScriptedProvider([{"type": "delta", "content": "ok"}])
    turn_input = _make_turn_input(provider, verbose_level=2)
    aggregator = ChatTurnAggregator()
    counter = _Counter()
    history = [{"role": "user", "content": "old"}]

    _ = [
        e
        async for e in _guarded_stream(
            turn_input=turn_input,
            history=history,
            system_prompt=None,
            per_turn_context=None,
            aggregator=aggregator,
            counter=counter,  # type: ignore[arg-type]
            hooks=[],
        )
    ]

    assert provider.stream_kwargs["history"] == history
    assert "codex_thread_id" not in provider.stream_kwargs


@pytest.mark.anyio
async def test_lightweight_codex_turn_still_runs_pre_turn_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active Recall must stay visible even when Codex uses compact prompting."""
    provider = _ScriptedProvider(
        [
            {"type": "delta", "content": "ok"},
            {"type": "done"},
        ]
    )
    hook_called = False

    async def recall_hook(_ctx: Any) -> str:
        nonlocal hook_called
        hook_called = True
        return "memory"

    async def no_persist(_turn_input: ChatTurnInput) -> tuple[list[dict[str, str]], Any]:
        return [], "assistant-id"

    async def no_finalize(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.channels.turn_runner._load_history_and_persist", no_persist)
    monkeypatch.setattr("app.channels.turn_runner._finalize_turn", no_finalize)

    turn_input = ChatTurnInput(
        conversation_id=MagicMock(),
        user_id=MagicMock(),
        question="hi",
        provider=provider,
        channel=_PassthroughChannel(),
        channel_message=MagicMock(),
        workspace_root=None,
        tools=[],
        pre_turn_hooks=[recall_hook],
        codex_thread_prompt_hash="hash",
        codex_lightweight_prompt=True,
    )

    _ = [chunk async for chunk in run_turn(turn_input)]

    assert hook_called is True
    assert provider.stream_kwargs["per_turn_context"] == "# PRE-TURN CONTEXT\n\nmemory"
    assert provider.stream_kwargs["reasoning_effort"] == "low"
