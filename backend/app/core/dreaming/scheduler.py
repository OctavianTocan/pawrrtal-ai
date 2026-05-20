"""Fire-and-forget scheduler for dreaming passes (#341).

The two trigger entry points the rest of the codebase calls are:

- :func:`schedule_session_end_dream` — fired by the per-turn finalizer
  when a conversation has been idle long enough to look like the
  user has wrapped up that thread.
- :func:`schedule_daily_rollup_dream` — fired by the daily cron (a
  follow-up to this PR) once per user, 24 h after the last rollup.

Both helpers create a :class:`DreamingJob` row in the
``pending`` state and launch the runner as a background task. The
runner takes over from there: it transitions the row through
``running`` → ``completed`` / ``failed`` and writes any new
memories. No locking is needed because the scope of each job is
(user_id, conversation_id) for ``session_end`` and (user_id,
24-hour window) for ``daily_rollup`` — concurrent runs at the
same scope would write the same dedupe-checked memories and the
classifier's substring filter swallows duplicates.

The strong-ref task set follows the same pattern as
:mod:`app.core.lcm.background` so background tasks aren't GC'd
mid-flight.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dreaming.runner import DreamFn, SessionFactory, run_dreaming_job
from app.models import DreamingJob

logger = logging.getLogger(__name__)

DreamingScope = Literal["session_end", "daily_rollup"]

# Strong references to in-flight tasks so asyncio's GC doesn't
# finalise them mid-loop. See app.core.lcm.background for the same
# pattern + rationale.
_DREAMING_TASKS: set[asyncio.Task[None]] = set()

# How long to wait after a completed dreaming pass for the same
# conversation before allowing another. Approximates the
# "idle window" behaviour from the ADR without an actual delayed
# scheduler: turns within this window count as the same session
# and don't re-trigger reflection. 30 minutes is the same default
# the ADR uses for the conceptual idle threshold.
_SESSION_END_THROTTLE_MINUTES = 30


async def schedule_session_end_dream(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID | None = None,
    dream_fn: DreamFn | None = None,
    session_factory: SessionFactory | None = None,
) -> uuid.UUID:
    """Create a session_end dreaming job and launch its runner.

    Returns the new job's id so the caller can correlate later
    log entries with it (e.g. surfacing "🌙 Pawrrtal dreamed about
    this conversation" in Telegram once the row hits ``completed``).
    """
    return await _create_and_schedule(
        session,
        user_id=user_id,
        scope="session_end",
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        dream_fn=dream_fn,
        session_factory=session_factory,
    )


async def schedule_session_end_dream_if_idle(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID | None = None,
    dream_fn: DreamFn | None = None,
    session_factory: SessionFactory | None = None,
    throttle_minutes: int = _SESSION_END_THROTTLE_MINUTES,
) -> uuid.UUID | None:
    """Schedule a session_end pass only if the conversation isn't recently reflected.

    Approximates the "idle window" trigger from the ADR without an
    actual delayed-task scheduler: the turn-runner fires this after
    every turn, and the throttle keeps consecutive turns inside the
    same session from spawning many redundant passes.

    Returns the new job's id when a pass was scheduled, or ``None``
    when the throttle filtered the call.
    """
    if await _has_recent_dreaming_pass(
        session,
        conversation_id=conversation_id,
        throttle_minutes=throttle_minutes,
    ):
        logger.debug(
            "DREAMING_TRIGGER_THROTTLED conversation_id=%s throttle_minutes=%s",
            conversation_id,
            throttle_minutes,
        )
        return None
    return await schedule_session_end_dream(
        session,
        user_id=user_id,
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        dream_fn=dream_fn,
        session_factory=session_factory,
    )


async def _has_recent_dreaming_pass(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    throttle_minutes: int,
) -> bool:
    """Return whether a recent dreaming job exists for ``conversation_id``.

    Both ``completed`` and any non-terminal status count — if a job
    is already running for this conversation we don't want a second
    racer in the same window.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=throttle_minutes)
    stmt = (
        select(DreamingJob.id)
        .where(DreamingJob.conversation_id == conversation_id)
        .where(DreamingJob.scope == "session_end")
        .where(DreamingJob.created_at >= cutoff)
        .order_by(desc(DreamingJob.created_at))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def schedule_daily_rollup_dream(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID | None = None,
    dream_fn: DreamFn | None = None,
    session_factory: SessionFactory | None = None,
) -> uuid.UUID:
    """Create a daily_rollup dreaming job and launch its runner."""
    return await _create_and_schedule(
        session,
        user_id=user_id,
        scope="daily_rollup",
        conversation_id=None,
        workspace_id=workspace_id,
        dream_fn=dream_fn,
        session_factory=session_factory,
    )


async def _create_and_schedule(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    scope: DreamingScope,
    conversation_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
    dream_fn: DreamFn | None,
    session_factory: SessionFactory | None,
) -> uuid.UUID:
    """Insert the job row and spawn the background runner.

    The job is committed before the task is launched so the runner
    can re-load it via its primary key — necessary because the
    runner opens its own session (life-cycle independent of the
    caller's).
    """
    job = DreamingJob(
        user_id=user_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        scope=scope,
        status="pending",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    job_id = job.id

    task = asyncio.create_task(
        run_dreaming_job(job_id, dream_fn=dream_fn, session_factory=session_factory),
        name=f"dreaming-{scope}-{job_id}",
    )
    _DREAMING_TASKS.add(task)
    task.add_done_callback(_DREAMING_TASKS.discard)
    logger.info(
        "DREAMING_JOB_SCHEDULED job_id=%s scope=%s user_id=%s conversation_id=%s",
        job_id,
        scope,
        user_id,
        conversation_id,
    )
    return job_id


__all__ = [
    "DreamingScope",
    "schedule_daily_rollup_dream",
    "schedule_session_end_dream",
    "schedule_session_end_dream_if_idle",
]
