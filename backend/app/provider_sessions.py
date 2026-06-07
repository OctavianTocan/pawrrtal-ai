"""Generic provider session persistence and turn-state helpers.

Provider sessions are opaque continuity handles owned by a provider runtime:
Codex SDK threads, Antigravity CLI conversations, or future plugin-provided
session handles. Core turn orchestration stores and forwards the handle without
knowing the provider's native name for it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import exc as sa_exc
from sqlalchemy import select, update

from app.infrastructure.database.legacy import async_session_maker
from app.models import Conversation

logger = logging.getLogger(__name__)

_PENDING_PROVIDER_SESSION_PERSIST_TASKS: set[asyncio.Task[None]] = set()
_DEFAULT_PERSIST_DRAIN_TIMEOUT_S: float = 10.0


@dataclass(frozen=True)
class ProviderSessionRecord:
    """Persisted opaque session state for one conversation."""

    kind: str | None
    session_id: str | None
    fingerprint: str | None


@dataclass(frozen=True)
class ProviderSessionTurnState:
    """Provider-prepared session behavior for one turn.

    ``stream_kwargs`` carries provider-native argument names. The turn runner
    does not inspect those keys; it forwards them only to the concrete provider
    that prepared the state.
    """

    kind: str | None = None
    session_id: str | None = None
    fingerprint: str | None = None
    stream_kwargs: dict[str, Any] = field(default_factory=dict)
    per_turn_context_kwarg: str | None = None
    omit_history: bool = False
    force_low_reasoning: bool = False


def _register_provider_session_persist_task(task: asyncio.Task[None]) -> None:
    """Track an in-flight provider-session persist task for shutdown drain."""
    _PENDING_PROVIDER_SESSION_PERSIST_TASKS.add(task)
    task.add_done_callback(_PENDING_PROVIDER_SESSION_PERSIST_TASKS.discard)


async def await_pending_provider_session_persist_tasks(
    timeout: float = _DEFAULT_PERSIST_DRAIN_TIMEOUT_S,  # noqa: ASYNC109 - lifespan drain API
) -> None:
    """Wait for in-flight provider-session writes to finish."""
    if not _PENDING_PROVIDER_SESSION_PERSIST_TASKS:
        return
    pending = list(_PENDING_PROVIDER_SESSION_PERSIST_TASKS)
    try:
        async with asyncio.timeout(timeout):
            await asyncio.gather(*pending, return_exceptions=True)
    except TimeoutError:
        outstanding = [task for task in pending if not task.done()]
        logger.warning(
            "provider_session: shutdown drain timed out after %.1fs; %d persist task(s) still running",
            timeout,
            len(outstanding),
        )


async def persist_provider_session(
    conversation_id: uuid.UUID,
    *,
    kind: str | None,
    session_id: str | None,
    fingerprint: str | None = None,
) -> None:
    """Persist an opaque provider session handle for future turns."""
    try:
        async with async_session_maker() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(
                    provider_session_kind=kind,
                    provider_session_id=session_id,
                    provider_session_fingerprint=fingerprint,
                )
            )
            await session.commit()
            logger.debug(
                "provider_session: persisted kind=%s session_id=%s conversation=%s",
                kind,
                session_id,
                conversation_id,
            )
    except (sa_exc.OperationalError, sa_exc.IntegrityError):
        logger.exception(
            "provider_session: failed to persist session for conversation %s",
            conversation_id,
        )


async def load_provider_session(conversation_id: uuid.UUID) -> ProviderSessionRecord | None:
    """Load the provider session record for a conversation."""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(
                    Conversation.provider_session_kind,
                    Conversation.provider_session_id,
                    Conversation.provider_session_fingerprint,
                ).where(Conversation.id == conversation_id)
            )
            row = result.first()
            if row is None:
                return None
            return ProviderSessionRecord(
                kind=row[0],
                session_id=row[1],
                fingerprint=row[2],
            )
    except sa_exc.OperationalError:
        logger.exception(
            "provider_session: failed to load session for conversation %s",
            conversation_id,
        )
        return None
