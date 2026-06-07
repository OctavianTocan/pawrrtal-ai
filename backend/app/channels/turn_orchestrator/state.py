"""Conversation state and shutdown-drain helpers for provider runtimes."""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import exc as sa_exc
from sqlalchemy import select, update

from app.infrastructure.database.legacy import async_session_maker
from app.models import Conversation

logger = logging.getLogger(__name__)

# Strong references to in-flight codex_thread_id persist tasks so they
# survive (a) GC, and (b) cancellation of the streaming response.  The
# UPDATE itself is small (~1 ms) but a SIGTERM mid-stream cancels every
# awaitable in the request task tree; without an independent task here,
# the multi-turn Codex thread id would be silently lost between turns.
# Drained at app shutdown via ``await_pending_codex_persist_tasks``
# (called from ``main.lifespan``'s finally block).
_PENDING_CODEX_PERSIST_TASKS: set[asyncio.Task[None]] = set()
_PENDING_TURN_FINALIZE_TASKS: set[asyncio.Task[None]] = set()

# Soft cap on the shutdown drain timeout. The UPDATE is small enough
# that 10 s is generous; tests can override.
_DEFAULT_PERSIST_DRAIN_TIMEOUT_S: float = 10.0


def _register_codex_persist_task(task: asyncio.Task[None]) -> None:
    """Track an in-flight persist task so shutdown can await it."""
    _PENDING_CODEX_PERSIST_TASKS.add(task)
    task.add_done_callback(_PENDING_CODEX_PERSIST_TASKS.discard)


def _register_turn_finalize_task(task: asyncio.Task[None]) -> None:
    """Track an in-flight turn finalizer so cancellation cannot GC it."""
    _PENDING_TURN_FINALIZE_TASKS.add(task)
    task.add_done_callback(_PENDING_TURN_FINALIZE_TASKS.discard)


async def await_pending_codex_persist_tasks(
    timeout: float = _DEFAULT_PERSIST_DRAIN_TIMEOUT_S,  # noqa: ASYNC109 — public shutdown drain; bound is the API
) -> None:
    """Wait for in-flight Codex thread-id persist tasks to finish.

    Called from the FastAPI lifespan shutdown handler so a graceful
    SIGTERM can complete the in-flight UPDATEs before the event loop
    exits. The ``timeout`` parameter caps how long shutdown will block;
    a soft warning surfaces when the deadline is exceeded so operators
    can correlate dropped thread ids with the shutdown event.

    ASYNC109 is intentional here — the drain is a public lifespan-
    shutdown surface where callers want a single bound on how long the
    cleanup can block. Wrapping with ``asyncio.timeout`` internally
    keeps the contract caller-friendly.
    """
    if not _PENDING_CODEX_PERSIST_TASKS:
        return
    pending = list(_PENDING_CODEX_PERSIST_TASKS)
    try:
        async with asyncio.timeout(timeout):
            await asyncio.gather(*pending, return_exceptions=True)
    except TimeoutError:
        # Surface the drop loud — operators need to know thread ids
        # may be lost from this shutdown cycle.
        outstanding = [t for t in pending if not t.done()]
        logger.warning(
            "codex: shutdown drain timed out after %.1fs; %d persist task(s) still running",
            timeout,
            len(outstanding),
        )


async def persist_codex_thread_id(
    conversation_id: uuid.UUID,
    thread_id: str | None,
    prompt_hash: str | None = None,
) -> None:
    """Persist a newly created Codex thread id against the conversation.

    Called inline from the streaming wrapper when the openai_codex
    provider emits a ``codex_thread_created`` internal signal. The call
    is awaited (not fire-and-forget) so a graceful shutdown can't cancel
    the write mid-flight and silently lose multi-turn Codex context.
    A single small UPDATE is fast enough that the per-event latency
    impact is negligible, and the signal is emitted at most once per
    conversation (when the Codex thread is first created).
    """
    try:
        async with async_session_maker() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(codex_thread_id=thread_id, codex_thread_prompt_hash=prompt_hash)
            )
            await session.commit()
            logger.debug(
                "codex: persisted thread_id=%s for conversation=%s",
                thread_id,
                conversation_id,
            )
    except (sa_exc.OperationalError, sa_exc.IntegrityError):
        logger.exception("codex: failed to persist thread_id for conversation %s", conversation_id)


async def load_codex_thread_id(conversation_id: uuid.UUID) -> str | None:
    """Load the persisted Codex thread id for resume support (if any)."""
    state = await load_codex_thread_state(conversation_id)
    return state[0] if state else None


async def load_codex_thread_state(
    conversation_id: uuid.UUID,
) -> tuple[str | None, str | None] | None:
    """Load the persisted Codex thread id and prompt hash for resume support."""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Conversation.codex_thread_id, Conversation.codex_thread_prompt_hash).where(
                    Conversation.id == conversation_id
                )
            )
            row = result.first()
            return (row[0], row[1]) if row else None
    except sa_exc.OperationalError:
        logger.exception("codex: failed to load thread state for conversation %s", conversation_id)
        return None


async def persist_agy_conversation_id(
    conversation_id: uuid.UUID,
    agy_conversation_id: str,
) -> None:
    """Persist the native Antigravity conversation id for future ``--conversation`` turns."""
    try:
        async with async_session_maker() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(agy_conversation_id=agy_conversation_id)
            )
            await session.commit()
            logger.debug(
                "agy: persisted conversation_id=%s for conversation=%s",
                agy_conversation_id,
                conversation_id,
            )
    except (sa_exc.OperationalError, sa_exc.IntegrityError):
        logger.exception(
            "agy: failed to persist native conversation id for conversation %s",
            conversation_id,
        )


async def load_agy_conversation_id(conversation_id: uuid.UUID) -> str | None:
    """Load the persisted Antigravity conversation id for resume support."""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Conversation.agy_conversation_id).where(Conversation.id == conversation_id)
            )
            row = result.first()
            return row[0] if row else None
    except sa_exc.OperationalError:
        logger.exception(
            "agy: failed to load native conversation id for conversation %s",
            conversation_id,
        )
        return None
