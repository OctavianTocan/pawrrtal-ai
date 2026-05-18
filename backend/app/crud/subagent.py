"""CRUD helpers for the ``subagents`` table.

Three concerns live in this module:

  1. **Insert** — :func:`insert_running_subagent` is what
     ``spawn_subagent.execute`` (PR 4) calls to atomically claim a
     handle and persist the parent's choices (persona, tools granted,
     parent message + parent subagent FKs).
  2. **Finalise** — :func:`finalize_subagent` transitions a row from
     ``running`` to a terminal status with result, error, cost, and
     ``completed_at``.  Called by the background runner (PR 3) when
     its child ``provider.stream()`` exhausts.
  3. **Cascade cancel** —
     :func:`cancel_running_subagents_for_conversation` is called from
     :func:`app.crud.conversation.delete_conversation` *before* the
     row is removed so the database CASCADE doesn't lose the
     audit trail of which child died for what reason.  This module
     only marks the row; killing the live ``asyncio.Task`` belongs to
     PR 3's in-process registry.

These helpers are intentionally small and side-effect-free beyond the
SQL they emit.  The runner / tools / chat router consume them; no
async I/O, no provider calls, no closure-over-request-state.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subagent, SubagentStatus
from app.subagent_models import SUBAGENT_TERMINAL_STATUSES

logger = logging.getLogger(__name__)


# Reason recorded in ``error`` when the cascade-cancel hook fires —
# stable string the frontend / audit query can match on.
CASCADE_CANCEL_REASON: str = "conversation deleted"


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------


async def insert_running_subagent(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    parent_user_id: uuid.UUID,
    persona_name: str,
    handle: str,
    task: str,
    tools_granted: Sequence[str],
    spawned_at: datetime,
    depth: int = 0,
    parent_message_id: uuid.UUID | None = None,
    parent_subagent_id: uuid.UUID | None = None,
    label: str | None = None,
) -> Subagent:
    """Insert a new ``status="running"`` subagent row and return it.

    Does not commit — callers compose this with their own transaction
    (the spawn tool commits inside its own session, the cancel hook
    commits as part of the conversation-delete transaction).
    """
    row = Subagent(
        conversation_id=conversation_id,
        parent_user_id=parent_user_id,
        parent_message_id=parent_message_id,
        parent_subagent_id=parent_subagent_id,
        depth=depth,
        persona_name=persona_name,
        handle=handle,
        label=label,
        task=task,
        status="running",
        tools_granted=list(tools_granted),
        spawned_at=spawned_at,
    )
    session.add(row)
    await session.flush()  # populate row.id without committing.
    return row


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


async def get_subagent_by_handle(session: AsyncSession, *, handle: str) -> Subagent | None:
    """Look up a subagent row by its stable short handle."""
    stmt = select(Subagent).where(Subagent.handle == handle)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_subagents_for_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    status_filter: str | None = None,
) -> list[Subagent]:
    """Return every subagent attached to ``conversation_id``.

    When ``status_filter`` is set, only rows matching that status are
    returned (used by :func:`cancel_running_subagents_for_conversation`
    and by the ``list_subagents`` tool's ``status="running"`` filter).
    Rows come back oldest-first so the UI can render them in spawn
    order without an extra sort.
    """
    stmt = select(Subagent).where(Subagent.conversation_id == conversation_id)
    if status_filter is not None:
        stmt = stmt.where(Subagent.status == status_filter)
    stmt = stmt.order_by(Subagent.spawned_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_running_for_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> int:
    """Return the count of ``running`` subagents in the conversation.

    Used at spawn time to enforce
    ``settings.subagent_max_concurrent_per_conversation``.
    """
    stmt = (
        select(func.count())
        .select_from(Subagent)
        .where(Subagent.conversation_id == conversation_id)
        .where(Subagent.status == "running")
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


# ---------------------------------------------------------------------------
# Finalise
# ---------------------------------------------------------------------------


async def finalize_subagent(
    session: AsyncSession,
    *,
    subagent_id: uuid.UUID,
    status: SubagentStatus,
    completed_at: datetime,
    result: str | None = None,
    error: str | None = None,
    cost_usd: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> bool:
    """Transition a running subagent to a terminal status.

    Idempotent at the database level via the
    ``status == 'running'`` filter on the UPDATE: a second call (e.g.
    cascade-cancel arriving after the runner already finalised the
    row) is a no-op rather than a stomp.  Returns ``True`` if the
    UPDATE matched a row, ``False`` if the row was already terminal.

    Does not commit — same transaction-composition contract as
    :func:`insert_running_subagent`.
    """
    if status not in SUBAGENT_TERMINAL_STATUSES:
        raise ValueError(
            f"finalize_subagent called with non-terminal status {status!r}; "
            f"expected one of {sorted(SUBAGENT_TERMINAL_STATUSES)}."
        )
    stmt = (
        update(Subagent)
        .where(Subagent.id == subagent_id)
        .where(Subagent.status == "running")
        .values(
            status=status,
            result=result,
            error=error,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            completed_at=completed_at,
        )
    )
    res = await session.execute(stmt)
    return (res.rowcount or 0) > 0


# ---------------------------------------------------------------------------
# Cascade cancel (called from delete_conversation)
# ---------------------------------------------------------------------------


async def cancel_running_subagents_for_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    reason: str = CASCADE_CANCEL_REASON,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    """Mark every ``running`` subagent in the conversation as cancelled.

    Returns the list of subagent IDs that were updated so the caller
    (and PR 3's in-process registry) can also cancel the matching
    ``asyncio.Task`` references — best-effort, since live refs only
    exist on the worker that spawned them.  The DB row is the
    authoritative signal: the runner re-reads ``status`` between
    iterations and bails when it sees anything other than ``running``.

    Does not commit — see the module docstring's transaction
    composition note.  ``conversation.delete_conversation`` calls this
    immediately before ``session.delete(conversation)`` so both writes
    land in one transaction; if the delete rolls back the cancel does
    too.
    """
    # Model column is naive ``DateTime`` (matches the LCM tables and the
    # rest of the schema).  Build a tz-aware UTC value first so the
    # deprecation gate stays clean, then strip the tz for the column.
    stamp = now or datetime.now(UTC).replace(tzinfo=None)
    # Collect the IDs first so we can return them after the UPDATE.
    select_stmt = (
        select(Subagent.id)
        .where(Subagent.conversation_id == conversation_id)
        .where(Subagent.status == "running")
    )
    res = await session.execute(select_stmt)
    cancelled_ids: list[uuid.UUID] = [row[0] for row in res.all()]
    if not cancelled_ids:
        return []
    update_stmt = (
        update(Subagent)
        .where(Subagent.id.in_(cancelled_ids))
        .values(
            status="cancelled",
            error=reason,
            completed_at=stamp,
        )
    )
    await session.execute(update_stmt)
    logger.info(
        "SUBAGENT_CASCADE_CANCEL conversation_id=%s count=%d reason=%s",
        conversation_id,
        len(cancelled_ids),
        reason,
    )
    return cancelled_ids


__all__ = [
    "CASCADE_CANCEL_REASON",
    "cancel_running_subagents_for_conversation",
    "count_running_for_conversation",
    "finalize_subagent",
    "get_subagent_by_handle",
    "insert_running_subagent",
    "list_subagents_for_conversation",
]
