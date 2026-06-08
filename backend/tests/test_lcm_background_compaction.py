"""LCM background compaction scheduling tests."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import Counter
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chat.aggregator import ChatTurnAggregator
from app.infrastructure.database.legacy import User
from app.models import LCMSummary
from app.turns.pipeline import ChatTurnInput, _finalize_turn
from tests.lcm_helpers import (
    make_conversation,
    make_fake_provider,
    patch_summary_provider,
    seed_context,
)

pytestmark = pytest.mark.anyio


async def test_schedule_lcm_compaction_runs_background_task_under_lock(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.lcm.background as bg_mod

    conv = await make_conversation(db_session, test_user)
    conv_id = conv.id
    await seed_context(
        db_session,
        test_user,
        conv,
        [("user", "msg0"), ("assistant", "msg1"), ("user", "msg2")],
    )
    monkeypatch.setattr(bg_mod.settings, "lcm_enabled", True)
    monkeypatch.setattr(bg_mod.settings, "lcm_fresh_tail_count", 2)
    monkeypatch.setattr(bg_mod.settings, "lcm_leaf_chunk_tokens", 100_000)
    patch_summary_provider(monkeypatch, make_fake_provider("compacted"))
    monkeypatch.setattr(
        bg_mod,
        "async_session_maker",
        async_sessionmaker(db_session.bind, expire_on_commit=False),
    )
    bg_mod._LCM_COMPACT_TASKS.clear()

    bg_mod.schedule_lcm_compaction(
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
    )

    assert len(bg_mod._LCM_COMPACT_TASKS) == 1
    while bg_mod._LCM_COMPACT_TASKS:
        await asyncio.gather(*list(bg_mod._LCM_COMPACT_TASKS))
    assert len(bg_mod._LCM_COMPACT_TASKS) == 0
    db_session.expire_all()
    summaries = (
        (await db_session.execute(select(LCMSummary).where(LCMSummary.conversation_id == conv_id)))
        .scalars()
        .all()
    )
    assert len(summaries) == 1
    assert summaries[0].content == "compacted"


async def test_schedule_lcm_compaction_serializes_concurrent_calls(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.lcm.background as bg_mod

    conv = await make_conversation(db_session, test_user)
    await seed_context(
        db_session,
        test_user,
        conv,
        [("user", "msg0"), ("assistant", "msg1"), ("user", "msg2")],
    )
    monkeypatch.setattr(bg_mod.settings, "lcm_enabled", True)
    monkeypatch.setattr(bg_mod.settings, "lcm_fresh_tail_count", 2)
    monkeypatch.setattr(bg_mod.settings, "lcm_leaf_chunk_tokens", 100_000)
    monkeypatch.setattr(
        bg_mod,
        "async_session_maker",
        async_sessionmaker(db_session.bind, expire_on_commit=False),
    )
    active_runs = 0
    max_concurrent = 0

    async def mock_compact_leaf(*_args: Any, **_kwargs: Any) -> bool:
        nonlocal active_runs, max_concurrent
        active_runs += 1
        max_concurrent = max(max_concurrent, active_runs)
        await asyncio.sleep(0.05)
        active_runs -= 1
        return True

    monkeypatch.setattr(bg_mod, "compact_leaf_if_needed", mock_compact_leaf)
    bg_mod._LCM_COMPACT_TASKS.clear()

    for _ in range(2):
        bg_mod.schedule_lcm_compaction(
            conversation_id=conv.id,
            user_id=test_user.id,
            model_id="gemini-2.5-flash",
        )

    assert len(bg_mod._LCM_COMPACT_TASKS) == 2
    while bg_mod._LCM_COMPACT_TASKS:
        await asyncio.gather(*list(bg_mod._LCM_COMPACT_TASKS))
    assert max_concurrent == 1
    assert active_runs == 0


async def test_schedule_lcm_compaction_disabled_is_noop(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.lcm.background as bg_mod

    conv = await make_conversation(db_session, test_user)
    monkeypatch.setattr(bg_mod.settings, "lcm_enabled", False)
    bg_mod._LCM_COMPACT_TASKS.clear()

    bg_mod.schedule_lcm_compaction(
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
    )

    assert len(bg_mod._LCM_COMPACT_TASKS) == 0


async def test_finalize_turn_triggers_lcm_compaction(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conv = await make_conversation(db_session, test_user)
    monkeypatch.setattr(
        "app.turns.pipeline.finalize.finalize_assistant_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.turns.pipeline.finalize.record_turn_cost_if_enabled",
        AsyncMock(),
    )
    monkeypatch.setattr("app.turns.pipeline.finalize.publish_if_available", AsyncMock())
    schedule_mock = MagicMock()

    class _MemoryBackend:
        def schedule_compaction(self, **kwargs: Any) -> None:
            schedule_mock(**kwargs)

    monkeypatch.setattr(
        "app.turns.pipeline.finalize.resolve_conversation_memory",
        MagicMock(return_value=SimpleNamespace(backend=_MemoryBackend())),
    )
    turn_input = ChatTurnInput(
        conversation_id=conv.id,
        user_id=test_user.id,
        question="hello",
        provider=MagicMock(),
        channel=MagicMock(),
        channel_message=cast(Any, {"model_id": "gemini-2.5-flash", "surface": "telegram"}),
        db_session=db_session,
    )

    await _finalize_turn(
        turn_input=turn_input,
        aggregator=ChatTurnAggregator(),
        assistant_message_id=uuid.uuid4(),
        started_at=time.perf_counter(),
        event_count=0,
        event_breakdown=Counter(),
        ttft_ms=None,
    )

    schedule_mock.assert_called_once_with(
        conversation_id=conv.id,
        user_id=test_user.id,
        model_id="gemini-2.5-flash",
    )
