"""Tests for the subagent background runner + reaper.

Per ``.claude/rules/testing/agent-loop-testing-philosophy.md``:

  * The agent-loop's own behaviour (safety, tool dispatch, context
    accumulation) is exercised elsewhere via ``ScriptedStreamFn``;
    this file is one layer above — it tests the runner's orchestration
    around ``provider.stream()``.
  * For that layer a tiny inline ``FakeProvider`` that emits known
    ``StreamEvent``s is the right shape: it lets us drive the
    runner's cost-aggregator chain, cancellation, and timeout paths
    deterministically without booting a real Gemini or Claude SDK.
    Same role as the "inline FailingProvider" the rule mentions.

Coverage:

  * Happy-path: provider emits text + usage; row finalised
    ``succeeded`` with non-zero cost; cost-ledger row written;
    completion event published.
  * Cancellation: task cancelled mid-stream; row finalised
    ``cancelled`` with stable reason; ``CancelledError`` propagates
    out so the registry's ``done_callback`` runs.
  * Timeout: persona ``max_wall_clock_seconds`` exceeded; row
    finalised ``failed`` with stable reason.
  * Provider error: row finalised ``failed``; phantom row does not
    survive.
  * Reaper: orphaned ``running`` rows are marked ``failed`` with the
    reaper reason on boot.
  * Registry: live handles tracked while running; cleared on
    completion via ``done_callback``.
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import EventBus
from app.core.event_bus.global_bus import set_event_bus
from app.core.providers.base import StreamEvent
from app.core.subagents import persona as persona_module
from app.core.subagents.events import SubagentCompletedEvent
from app.core.subagents.persona import Persona
from app.core.subagents.registry import clear as clear_registry
from app.core.subagents.registry import is_alive, live_handles
from app.core.subagents.runner import SUBAGENT_COST_SURFACE, start_subagent
from app.core.subagents.startup import REAPER_ERROR_REASON, reap_orphaned_subagents
from app.crud.subagent import get_subagent_by_handle, insert_running_subagent
from app.db import User
from app.governance_models import CostLedger
from app.models import Conversation, Workspace

# ---------------------------------------------------------------------------
# Constants for the inline FakeProvider scenarios
# ---------------------------------------------------------------------------


_FAKE_INPUT_TOKENS: int = 12
_FAKE_OUTPUT_TOKENS: int = 34
_FAKE_COST_USD: float = 0.0042

_FAST_WALL_CLOCK_SECONDS: float = 1.0
_RUNAWAY_PROVIDER_HANG_SECONDS: float = 5.0


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch) -> None:
    """Each test starts with an empty in-process registry and bus."""
    clear_registry()
    set_event_bus(None)


@pytest.fixture
async def event_bus() -> AsyncIterator[EventBus]:
    """Spin up a real event bus and stash it in the global slot.

    The runner publishes via :func:`publish_if_available`, which reads
    the global slot.  Setting it here means tests can subscribe to the
    completion event without mocking the publish call.
    """
    bus = EventBus()
    await bus.start()
    set_event_bus(bus)
    try:
        yield bus
    finally:
        set_event_bus(None)
        await bus.stop()


@pytest.fixture
async def seeded_workspace(db_session: AsyncSession, test_user: User) -> Workspace:
    """Workspace dir on disk so build_chat_permission_check has a root."""
    workspace_root = Path(tempfile.mkdtemp(prefix="pawrrtal-subagent-test-"))
    workspace = Workspace(
        id=uuid4(),
        user_id=test_user.id,
        name="Main",
        slug="main",
        path=str(workspace_root),
        is_default=True,
    )
    db_session.add(workspace)
    await db_session.commit()
    return workspace


def _build_test_persona(*, model: str | None = None, wall_clock: float = 30.0) -> Persona:
    """Build a Persona instance for tests without going through the loader.

    Skips the YAML/file step — the loader is covered in
    ``test_subagent_persona.py``.  Uses the catalog's canonical default
    when no model is supplied so production model resolution works.
    """
    return Persona(
        name="tester",
        description="A persona used by runner tests.",
        model=model or "google/gemini-3-flash-preview",
        tools_allow=frozenset(),
        system_prompt="You are a test subagent.",
        max_iterations=10,
        max_wall_clock_seconds=wall_clock,
        default_reasoning_effort=None,
        source_path=Path("/tmp/test-persona.md"),
    )


# ---------------------------------------------------------------------------
# Inline FakeProviders — narrow stubs per test concern
# ---------------------------------------------------------------------------


class _SuccessProvider:
    """Emits a delta + usage event then completes — happy-path fixture."""

    async def stream(self, *_args, **_kwargs) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="delta", content="hello from subagent")
        yield StreamEvent(
            type="usage",
            input_tokens=_FAKE_INPUT_TOKENS,
            output_tokens=_FAKE_OUTPUT_TOKENS,
            cost_usd=_FAKE_COST_USD,
        )


class _HangingProvider:
    """Sleeps forever — used to exercise timeout and cancellation paths."""

    async def stream(self, *_args, **_kwargs) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="delta", content="starting...")
        await asyncio.sleep(_RUNAWAY_PROVIDER_HANG_SECONDS)
        yield StreamEvent(type="delta", content="never reached")


class _ExplodingProvider:
    """Raises mid-stream — exercises the runner's broad except."""

    async def stream(self, *_args, **_kwargs) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="delta", content="about to crash")
        raise RuntimeError("synthetic provider failure")


def _patch_resolve_llm(monkeypatch, provider) -> None:
    """Make ``resolve_llm`` always return our fake instance.

    Patched on the runner module's import binding because that's the
    actual call site (Python looks up names against the importing
    module's globals at call time).
    """
    monkeypatch.setattr("app.core.subagents.runner.resolve_llm", lambda *a, **k: provider)


# ---------------------------------------------------------------------------
# Happy path — drains cost into the ledger
# ---------------------------------------------------------------------------


def _fixture_session_maker(db_session: AsyncSession):
    """Return a callable that yields the test's in-memory fixture session.

    Production wires ``app.db.async_session_maker`` which opens its own
    engine; the fixture builds a separate in-memory SQLite, so the
    runner has to be told to reuse the fixture session or it'll write
    into a different empty database and assertions fail with "no such
    table".
    """
    from contextlib import asynccontextmanager  # noqa: PLC0415

    @asynccontextmanager
    async def maker():
        yield db_session

    return maker


async def _seed_and_run(
    *,
    db_session: AsyncSession,
    test_user: User,
    seeded_workspace: Workspace,
    provider,
    monkeypatch,
    persona: Persona,
    handle: str = "tester#01",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed conversation + subagent row, schedule the runner, await it.

    Returns ``(conversation_id, subagent_id)`` so the assertions can
    re-query the DB.
    """
    convo = Conversation(
        id=uuid4(),
        user_id=test_user.id,
        title="Subagent test",
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(convo)
    await db_session.commit()

    row = await insert_running_subagent(
        db_session,
        conversation_id=convo.id,
        parent_user_id=test_user.id,
        persona_name=persona.name,
        handle=handle,
        task="do a thing",
        tools_granted=[],
        spawned_at=_now(),
    )
    await db_session.commit()

    _patch_resolve_llm(monkeypatch, provider)

    task = await start_subagent(
        subagent_id=row.id,
        handle=handle,
        conversation_id=convo.id,
        user_id=test_user.id,
        workspace_root=Path(seeded_workspace.path),
        surface="web",
        persona=persona,
        task="do a thing",
        child_tools=[],
        session_maker=_fixture_session_maker(db_session),
    )
    await task
    return convo.id, row.id


@pytest.mark.anyio
async def test_runner_happy_path_finalises_and_writes_cost_ledger(
    db_session: AsyncSession,
    test_user: User,
    seeded_workspace: Workspace,
    monkeypatch,
) -> None:
    """End-to-end: provider yields usage; row + ledger reflect it.

    This is the test the grumpy reviewer demanded — proves the
    subagent's spend lands on the cost ledger so the daily cap
    counts it.
    """
    monkeypatch.setattr("app.core.subagents.runner.settings.cost_tracker_enabled", True)
    persona = _build_test_persona()

    conv_id, subagent_id = await _seed_and_run(
        db_session=db_session,
        test_user=test_user,
        seeded_workspace=seeded_workspace,
        provider=_SuccessProvider(),
        monkeypatch=monkeypatch,
        persona=persona,
    )

    fetched = await get_subagent_by_handle(db_session, handle="tester#01")
    assert fetched is not None
    assert fetched.status == "succeeded"
    assert fetched.result == "hello from subagent"
    assert fetched.cost_usd == pytest.approx(_FAKE_COST_USD)
    assert fetched.input_tokens == _FAKE_INPUT_TOKENS
    assert fetched.output_tokens == _FAKE_OUTPUT_TOKENS
    assert fetched.completed_at is not None

    # Cost ledger row was written under the documented surface label.
    from sqlalchemy import select

    ledger_rows = (
        (await db_session.execute(select(CostLedger).where(CostLedger.conversation_id == conv_id)))
        .scalars()
        .all()
    )
    assert len(ledger_rows) == 1
    assert ledger_rows[0].surface == SUBAGENT_COST_SURFACE
    assert ledger_rows[0].cost_usd == pytest.approx(_FAKE_COST_USD)
    assert ledger_rows[0].input_tokens == _FAKE_INPUT_TOKENS
    assert subagent_id == fetched.id  # sanity check the seed helper.


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_runner_cancellation_marks_row_cancelled(
    db_session: AsyncSession,
    test_user: User,
    seeded_workspace: Workspace,
    monkeypatch,
) -> None:
    """Cancelling the task mid-stream finalises the row as ``cancelled``."""
    monkeypatch.setattr("app.core.subagents.runner.settings.cost_tracker_enabled", False)
    persona = _build_test_persona(wall_clock=30.0)

    convo = Conversation(
        id=uuid4(),
        user_id=test_user.id,
        title="t",
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(convo)
    await db_session.commit()
    row = await insert_running_subagent(
        db_session,
        conversation_id=convo.id,
        parent_user_id=test_user.id,
        persona_name=persona.name,
        handle="hanging#02",
        task="hang forever",
        tools_granted=[],
        spawned_at=_now(),
    )
    await db_session.commit()

    _patch_resolve_llm(monkeypatch, _HangingProvider())
    task = await start_subagent(
        subagent_id=row.id,
        handle="hanging#02",
        conversation_id=convo.id,
        user_id=test_user.id,
        workspace_root=Path(seeded_workspace.path),
        surface="web",
        persona=persona,
        task="hang forever",
        child_tools=[],
        session_maker=_fixture_session_maker(db_session),
    )

    # Yield once so the runner enters the stream loop, then cancel.
    await asyncio.sleep(0.05)
    assert is_alive("hanging#02")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # done_callback should have cleared the registry by now.
    assert not is_alive("hanging#02")
    assert "hanging#02" not in live_handles()

    fetched = await get_subagent_by_handle(db_session, handle="hanging#02")
    assert fetched is not None
    assert fetched.status == "cancelled"
    assert fetched.error == "cancelled by parent"


# ---------------------------------------------------------------------------
# Timeout (persona max_wall_clock_seconds)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_runner_timeout_marks_row_failed(
    db_session: AsyncSession,
    test_user: User,
    seeded_workspace: Workspace,
    monkeypatch,
) -> None:
    """A persona with a tiny wall-clock + a hanging provider trips timeout."""
    monkeypatch.setattr("app.core.subagents.runner.settings.cost_tracker_enabled", False)
    persona = _build_test_persona(wall_clock=_FAST_WALL_CLOCK_SECONDS)

    _, _ = await _seed_and_run(
        db_session=db_session,
        test_user=test_user,
        seeded_workspace=seeded_workspace,
        provider=_HangingProvider(),
        monkeypatch=monkeypatch,
        persona=persona,
        handle="slow#03",
    )

    fetched = await get_subagent_by_handle(db_session, handle="slow#03")
    assert fetched is not None
    assert fetched.status == "failed"
    assert fetched.error is not None
    assert "max_wall_clock_seconds" in fetched.error


# ---------------------------------------------------------------------------
# Provider exception
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_runner_provider_exception_marks_row_failed(
    db_session: AsyncSession,
    test_user: User,
    seeded_workspace: Workspace,
    monkeypatch,
) -> None:
    """A provider that raises mid-stream surfaces as ``failed`` not ``running``."""
    monkeypatch.setattr("app.core.subagents.runner.settings.cost_tracker_enabled", False)
    persona = _build_test_persona()

    _, _ = await _seed_and_run(
        db_session=db_session,
        test_user=test_user,
        seeded_workspace=seeded_workspace,
        provider=_ExplodingProvider(),
        monkeypatch=monkeypatch,
        persona=persona,
        handle="boom#04",
    )

    fetched = await get_subagent_by_handle(db_session, handle="boom#04")
    assert fetched is not None
    assert fetched.status == "failed"
    assert fetched.error is not None
    assert "synthetic provider failure" in fetched.error


# ---------------------------------------------------------------------------
# Completion event publication
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_runner_publishes_completion_event(
    db_session: AsyncSession,
    test_user: User,
    seeded_workspace: Workspace,
    monkeypatch,
    event_bus: EventBus,
) -> None:
    """A subscriber receives one SubagentCompletedEvent per terminal turn."""
    monkeypatch.setattr("app.core.subagents.runner.settings.cost_tracker_enabled", False)
    received: list[SubagentCompletedEvent] = []
    completion_done = asyncio.Event()

    async def collect(event) -> None:
        received.append(event)
        completion_done.set()

    event_bus.subscribe(SubagentCompletedEvent, collect)

    persona = _build_test_persona()
    await _seed_and_run(
        db_session=db_session,
        test_user=test_user,
        seeded_workspace=seeded_workspace,
        provider=_SuccessProvider(),
        monkeypatch=monkeypatch,
        persona=persona,
        handle="event#05",
    )
    # Give the bus consumer a turn to dispatch.
    await asyncio.wait_for(completion_done.wait(), timeout=2.0)

    assert len(received) == 1
    ev = received[0]
    assert ev.handle == "event#05"
    assert ev.status == "succeeded"
    assert ev.cost_usd == pytest.approx(_FAKE_COST_USD)
    assert ev.persona_name == persona.name


# ---------------------------------------------------------------------------
# Startup reaper
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_reaper_marks_orphaned_rows_failed(db_session: AsyncSession, test_user: User) -> None:
    """A stale ``running`` row from a dead process becomes ``failed``."""
    convo = Conversation(
        id=uuid4(),
        user_id=test_user.id,
        title="t",
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(convo)
    await db_session.commit()
    await insert_running_subagent(
        db_session,
        conversation_id=convo.id,
        parent_user_id=test_user.id,
        persona_name="researcher",
        handle="orphan#06",
        task="never finished",
        tools_granted=[],
        spawned_at=_now(),
    )
    await db_session.commit()

    # Synthesize a session_maker that wraps the test session so the
    # reaper runs against the same in-memory DB.  Production passes
    # ``app.db.async_session_maker``; this test bridges the fixture.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fixture_session_maker() -> AsyncIterator[AsyncSession]:
        yield db_session

    rescued = await reap_orphaned_subagents(fixture_session_maker)
    assert rescued == 1

    fetched = await get_subagent_by_handle(db_session, handle="orphan#06")
    assert fetched is not None
    assert fetched.status == "failed"
    assert fetched.error == REAPER_ERROR_REASON


@pytest.mark.anyio
async def test_reaper_clean_boot_returns_zero(db_session: AsyncSession, test_user: User) -> None:
    """No orphans → reaper returns 0 without raising."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fixture_session_maker() -> AsyncIterator[AsyncSession]:
        yield db_session

    assert await reap_orphaned_subagents(fixture_session_maker) == 0


# ---------------------------------------------------------------------------
# Smoke check that the persona module wiring still resolves end-to-end
# ---------------------------------------------------------------------------


def test_runner_imports_resolve() -> None:
    """Sanity: the runner module imports cleanly + exposes its surface.

    Catches import-time mistakes (circular imports, missing symbols)
    that would otherwise hide until production first boot.
    """
    from app.core.subagents.runner import SUBAGENT_COST_SURFACE, start_subagent

    assert SUBAGENT_COST_SURFACE == "subagent"
    assert callable(start_subagent)
    # Persona module is the only sibling we should have imported.
    assert hasattr(persona_module, "Persona")
