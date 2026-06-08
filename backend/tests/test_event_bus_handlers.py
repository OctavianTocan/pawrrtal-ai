"""Tests for the agent handler and Telegram notification subscriber.

Both handlers are bus-driven so the tests publish events through a
real :class:`EventBus` and assert on the resulting side-effects.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.telegram.notifications import TelegramNotificationService
from app.infrastructure.database.legacy import User
from app.infrastructure.event_bus import (
    AgentHandler,
    AgentResponseEvent,
    EventBus,
    ScheduledEvent,
    WebhookEvent,
    global_bus,
)
from app.infrastructure.event_bus import handlers as event_handlers
from app.models import ChatMessage, Conversation, Workspace
from app.providers.base import AILLM, StreamEvent
from app.providers.selection import ProviderSelection

pytestmark = pytest.mark.anyio


_DRAIN_POLL_INTERVAL_S = 0.01
_DRAIN_DEFAULT_TIMEOUT_S = 0.5


async def _drain(bus: EventBus) -> None:
    """Wait briefly so the consumer task picks up published events."""
    deadline = asyncio.get_event_loop().time() + _DRAIN_DEFAULT_TIMEOUT_S
    while bus._queue.qsize() > 0:
        if asyncio.get_event_loop().time() > deadline:
            break
        await asyncio.sleep(_DRAIN_POLL_INTERVAL_S)
    await asyncio.sleep(_DRAIN_POLL_INTERVAL_S)


class _RecordingBot:
    """Minimal bot stub that records every ``send_message`` call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send_message(self, *, chat_id: str, text: str, **_kw: object) -> None:
        self.calls.append((chat_id, text))


class _FakeTurnProvider:
    """Provider stub used to prove event turns enter the Turn Pipeline."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        history: list[dict[str, str]] | None = None,
        tools: object = None,
        system_prompt: str | None = None,
        reasoning_effort: object = None,
        images: object = None,
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append(
            {
                "question": question,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "history": history,
                "tools": tools,
                "system_prompt": system_prompt,
                "reasoning_effort": reasoning_effort,
                "images": images,
            }
        )
        yield {"type": "delta", "content": "scheduled output"}


class TestTelegramNotificationDelivery:
    async def test_delivers_to_event_chat_id(self) -> None:
        bus = EventBus()
        await bus.start()
        bot = _RecordingBot()
        TelegramNotificationService(telegram_bot=bot).register(bus)
        await bus.publish(
            AgentResponseEvent(chat_id="42", text="hello", originating_event_id="abc")
        )
        await _drain(bus)
        await bus.stop()
        assert bot.calls == [("42", "hello")]

    async def test_skips_when_no_chat_id(self) -> None:
        """Without a chat_id the service no-ops (broadcast list is future work)."""
        bus = EventBus()
        await bus.start()
        bot = _RecordingBot()
        TelegramNotificationService(telegram_bot=bot).register(bus)
        await bus.publish(AgentResponseEvent(chat_id=None, text="hello"))
        await _drain(bus)
        await bus.stop()
        assert bot.calls == []

    async def test_skips_when_no_bot(self) -> None:
        """No bot configured → the service silently no-ops."""
        bus = EventBus()
        await bus.start()
        TelegramNotificationService(telegram_bot=None).register(bus)
        await bus.publish(AgentResponseEvent(chat_id="42", text="hello"))
        await _drain(bus)
        await bus.stop()
        # Nothing to assert beyond "didn't crash".

    async def test_truncates_oversize_text(self) -> None:
        """Text longer than the per-message budget is tail-truncated with an ellipsis."""
        bus = EventBus()
        await bus.start()
        bot = _RecordingBot()
        TelegramNotificationService(telegram_bot=bot).register(bus)
        long_text = "x" * 5000
        await bus.publish(AgentResponseEvent(chat_id="42", text=long_text))
        await _drain(bus)
        await bus.stop()
        assert len(bot.calls) == 1
        sent = bot.calls[0][1]
        assert sent.endswith("…")
        assert len(sent) <= 4000

    async def test_delivery_failure_isolated(self) -> None:
        """A bot-side exception is swallowed so it doesn't poison the bus."""

        class ExplodingBot:
            async def send_message(self, **_: object) -> None:
                raise RuntimeError("boom")

        bus = EventBus()
        await bus.start()
        TelegramNotificationService(telegram_bot=ExplodingBot()).register(bus)
        await bus.publish(AgentResponseEvent(chat_id="42", text="hello"))
        await _drain(bus)
        await bus.stop()
        # No assertion needed — the bus would have logged and moved on.


class TestAgentHandlerRouting:
    """The AgentHandler subscribes to webhook + scheduled events."""

    async def test_subscribes_to_both_event_types(self) -> None:
        bus = EventBus()
        AgentHandler().register(bus)
        # Internal check — the handler registered subscribers for
        # both event types, not just one.
        subs = bus._handlers
        assert WebhookEvent in subs
        assert ScheduledEvent in subs

    async def test_no_user_skips_publish(self) -> None:
        """Webhook with no user_id (and no default) skips silently."""
        bus = EventBus()
        await bus.start()
        bot = _RecordingBot()
        AgentHandler().register(bus)
        TelegramNotificationService(telegram_bot=bot).register(bus)
        await bus.publish(WebhookEvent(provider="github", event_type_name="push", payload={}))
        await _drain(bus)
        await bus.stop()
        # Without a user the agent never runs, so no notification.
        assert bot.calls == []

    async def test_scheduled_event_with_skill_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Scheduled event prompt shaping is passed to the targeted turn runner."""
        captured: dict[str, object] = {}

        async def fake_run_agent_turn(**kwargs: object) -> str:
            captured.update(kwargs)
            return "done"

        monkeypatch.setattr(event_handlers, "_run_agent_turn", fake_run_agent_turn)
        bus = EventBus()
        global_bus.set_event_bus(bus)
        await bus.start()
        try:
            responses: list[AgentResponseEvent] = []

            async def record_response(event: object) -> None:
                if isinstance(event, AgentResponseEvent):
                    responses.append(event)

            conversation_id = uuid.uuid4()
            user_id = uuid.uuid4()
            AgentHandler(default_user_id=user_id).register(bus)
            bus.subscribe(AgentResponseEvent, record_response)
            await bus.publish(
                ScheduledEvent(
                    job_id=uuid.uuid4(),
                    job_name="daily-summary",
                    prompt="Summarize my email.",
                    skill_name="triage",
                    target_chat_ids=["42"],
                    target_conversation_id=conversation_id,
                )
            )
            await _drain(bus)
        finally:
            global_bus.set_event_bus(None)
            await bus.stop()

        assert captured["user_id"] == user_id
        assert captured["conversation_id"] == conversation_id
        assert "Reminder Fired - daily-summary" in str(captured["prompt"])
        assert "/triage" in str(captured["prompt"])
        assert "Summarize my email." in str(captured["prompt"])
        assert len(responses) == 1
        assert responses[0].user_id == user_id
        assert responses[0].chat_id == "42"
        assert responses[0].text == "done"
        assert responses[0].originating_event_id == cast(str, captured["originating_event_id"])

    async def test_run_agent_turn_uses_turn_pipeline(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        seeded_default_workspace: Workspace,
        test_user: User,
    ) -> None:
        """Targeted event turns persist through the same runner as user chat."""
        now = datetime.now(UTC).replace(tzinfo=None)
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=test_user.id,
            title="Heartbeat",
            created_at=now,
            updated_at=now,
            model_id="agent-sdk:anthropic/claude-opus-4-7",
            reasoning_effort="low",
            verbose_level=2,
        )
        db_session.add(conversation)
        await db_session.commit()

        provider = _FakeTurnProvider()
        monkeypatch.setattr(
            "app.turns.pipeline.prepare.require_provider",
            lambda model_id, **_kwargs: ProviderSelection(
                provider=cast(AILLM, provider),
                effective_model_id=model_id,
            ),
        )

        @asynccontextmanager
        async def test_session_maker() -> AsyncIterator[AsyncSession]:
            yield db_session

        monkeypatch.setattr(event_handlers, "async_session_maker", test_session_maker)

        text = await event_handlers._run_agent_turn(
            prompt="Run the heartbeat.",
            user_id=test_user.id,
            conversation_id=conversation.id,
            originating_event_id="evt-123",
        )

        assert text == "scheduled output"
        assert len(provider.calls) == 1
        assert provider.calls[0]["question"] == "Run the heartbeat."
        assert provider.calls[0]["reasoning_effort"] == "low"

        result = await db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.ordinal)
        )
        messages = list(result.scalars())
        assert [(message.role, message.content) for message in messages] == [
            ("user", "Run the heartbeat."),
            ("assistant", "scheduled output"),
        ]
        assert messages[-1].assistant_status == "complete"
