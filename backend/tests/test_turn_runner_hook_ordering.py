"""Hook-ordering tests for ``_guarded_stream`` (#347 / #352 L3).

The verbose filter is a channel rendering concern; observability hooks
(agent trace / OTel span recorders) must see every event regardless of
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
from app.channels.turn_orchestrator import ChatTurnInput, _guarded_stream, run_turn
from app.chat.aggregator import ChatTurnAggregator
from app.plugins.adapters.turn_context import TurnContextProviderAdapter
from app.provider_sessions import ProviderSessionTurnState
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
        log_tag="TEST",
        log_extras={},
        verbose_level=verbose_level,
        reasoning_effort=None,
    )


def _make_codex_turn_input(provider: _ScriptedProvider) -> ChatTurnInput:
    """Build a turn input that simulates a provider-owned native session."""
    turn_input = _make_turn_input(provider, verbose_level=2)
    return ChatTurnInput(
        **{
            **turn_input.__dict__,
            "provider_session": ProviderSessionTurnState(
                kind="openai_codex",
                session_id="thr_existing",
                fingerprint="hash",
                stream_kwargs={"native_session_id": "thr_existing"},
                per_turn_context_kwarg="per_turn_context",
                omit_history=True,
            ),
        }
    )


def _make_agy_turn_input(provider: _ScriptedProvider) -> ChatTurnInput:
    """Build a turn input that simulates another provider-owned native session."""
    turn_input = _make_turn_input(provider, verbose_level=2)
    return ChatTurnInput(
        **{
            **turn_input.__dict__,
            "provider_session": ProviderSessionTurnState(
                kind="agy_cli",
                session_id="agy_existing",
                stream_kwargs={"native_conversation_id": "agy_existing"},
                omit_history=True,
            ),
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
    agent trace hook lives in the same ``hooks`` list and must observe
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
    """Provider-owned sessions can opt out of replaying app-side history."""
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
            per_turn_context="# TURN CONTEXT\n\nmemory",
            aggregator=aggregator,
            counter=counter,  # type: ignore[arg-type]
            hooks=[],
        )
    ]

    assert delivered == [{"type": "delta", "content": "ok"}]
    assert provider.stream_kwargs["history"] == []
    assert provider.stream_kwargs["native_session_id"] == "thr_existing"
    assert provider.stream_kwargs["per_turn_context"] == "# TURN CONTEXT\n\nmemory"


@pytest.mark.anyio
async def test_resumed_agy_conversation_does_not_replay_pawrrtal_history() -> None:
    """A second provider-owned session can also opt out of history replay."""
    provider = _ScriptedProvider([{"type": "delta", "content": "ok"}])
    turn_input = _make_agy_turn_input(provider)
    aggregator = ChatTurnAggregator()
    counter = _Counter()
    history = [{"role": "user", "content": "old"}]

    delivered = [
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

    assert delivered == [{"type": "delta", "content": "ok"}]
    assert provider.stream_kwargs["history"] == []
    assert provider.stream_kwargs["native_conversation_id"] == "agy_existing"


@pytest.mark.anyio
async def test_provider_session_created_event_is_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first native provider session event persists its id for later resumes."""
    provider = _ScriptedProvider(
        [
            {
                "type": "internal",
                "kind": "provider_session_created",
                "provider": "agy_cli",
                "session_id": "agy_new",
            },
            {"type": "delta", "content": "ok"},
        ]
    )
    turn_input = _make_turn_input(provider, verbose_level=2)
    aggregator = ChatTurnAggregator()
    counter = _Counter()
    persisted: list[tuple[Any, str | None, str | None, str | None]] = []

    async def fake_persist(
        conversation_id: Any,
        *,
        kind: str | None,
        session_id: str | None,
        fingerprint: str | None = None,
    ) -> None:
        persisted.append((conversation_id, kind, session_id, fingerprint))

    monkeypatch.setattr(
        "app.channels.turn_orchestrator.runner.persist_provider_session",
        fake_persist,
    )

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

    assert delivered == [{"type": "delta", "content": "ok"}]
    assert persisted == [(turn_input.conversation_id, "agy_cli", "agy_new", None)]


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
async def test_turn_without_provider_session_replays_pawrrtal_history() -> None:
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
    assert "native_session_id" not in provider.stream_kwargs


@pytest.mark.anyio
async def test_lightweight_codex_turn_still_runs_turn_context_providers(
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

    monkeypatch.setattr(
        "app.channels.turn_orchestrator.runner._load_history_and_persist", no_persist
    )
    monkeypatch.setattr("app.channels.turn_orchestrator.runner._finalize_turn", no_finalize)

    turn_input = ChatTurnInput(
        conversation_id=MagicMock(),
        user_id=MagicMock(),
        question="hi",
        provider=provider,
        channel=_PassthroughChannel(),
        channel_message={
            "conversation_id": MagicMock(),
            "metadata": {},
            "model_id": "openai-codex:openai/gpt-5.5",
            "surface": "telegram",
            "text": "hi",
            "user_id": MagicMock(),
        },
        workspace_root=None,
        tools=[],
        turn_context_providers=[
            TurnContextProviderAdapter(
                plugin_id="active_recall",
                capability_id="active_recall",
                title="Active Recall",
                order=100,
                timeout_seconds=10,
                provider=recall_hook,
            )
        ],
        provider_session=ProviderSessionTurnState(
            kind="openai_codex",
            fingerprint="hash",
            per_turn_context_kwarg="per_turn_context",
            omit_history=True,
            force_low_reasoning=True,
        ),
    )

    _ = [chunk async for chunk in run_turn(turn_input)]

    assert hook_called is True
    assert provider.stream_kwargs["per_turn_context"] == "# TURN CONTEXT\n\nmemory"
    assert "memory" in provider.stream_kwargs["system_prompt"]
    assert "## Tools available this turn" in provider.stream_kwargs["system_prompt"]
    assert provider.stream_kwargs["reasoning_effort"] == "low"


@pytest.mark.anyio
async def test_turn_context_provider_draft_updater_is_surface_agnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Context providers receive the generic draft callback from ``ChatTurnInput``."""
    provider = _ScriptedProvider(
        [
            {"type": "delta", "content": "ok"},
            {"type": "done"},
        ]
    )
    draft_updates: list[str] = []
    finished = False

    async def draft_updater(text: str) -> None:
        draft_updates.append(text)

    async def recall_hook(ctx: Any) -> str:
        assert ctx.draft_updater is draft_updater
        assert ctx.workspace_root is not None
        await ctx.draft_updater("checking memory")
        return "memory"

    async def on_finished() -> None:
        nonlocal finished
        finished = True

    async def no_persist(_turn_input: ChatTurnInput) -> tuple[list[dict[str, str]], Any]:
        return [], "assistant-id"

    async def no_finalize(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "app.channels.turn_orchestrator.runner._load_history_and_persist", no_persist
    )
    monkeypatch.setattr("app.channels.turn_orchestrator.runner._finalize_turn", no_finalize)

    turn_input = ChatTurnInput(
        conversation_id=MagicMock(),
        user_id=MagicMock(),
        question="hi",
        provider=provider,
        channel=_PassthroughChannel(),
        channel_message={
            "conversation_id": MagicMock(),
            "metadata": {},
            "model_id": "agent-sdk:anthropic/claude-opus-4-7",
            "surface": "web",
            "text": "hi",
            "user_id": MagicMock(),
        },
        workspace_root=None,
        tools=[],
        turn_context_providers=[
            TurnContextProviderAdapter(
                plugin_id="active_recall",
                capability_id="active_recall",
                title="Active Recall",
                order=100,
                timeout_seconds=10,
                provider=recall_hook,
            )
        ],
        draft_updater=draft_updater,
        on_turn_context_finished=on_finished,
    )

    _ = [chunk async for chunk in run_turn(turn_input)]

    assert draft_updates == ["checking memory"]
    assert finished is True
    assert "# TURN CONTEXT\n\nmemory" in provider.stream_kwargs["system_prompt"]
