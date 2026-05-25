"""APScheduler wrapper that publishes :class:`ScheduledEvent` on every fire.

Uses ``AsyncIOScheduler`` so triggers and the FastAPI event loop
share the same async context.  Persists the job catalogue in our
``scheduled_jobs`` Postgres table — APScheduler's own jobstore
isn't used because we want first-class CRUD over the catalogue
from the API (admin can list, edit, soft-delete jobs without
touching APScheduler internals).

On boot:
1. ``start()`` reads every ``is_active=True`` row from
   ``scheduled_jobs`` and re-registers a cron trigger for each.
2. APScheduler fires → ``_fire_event()`` builds + publishes a
   ``ScheduledEvent`` and updates the row's ``last_fired_at``.

Configuration:
* ``settings.scheduler_enabled`` — master switch
* The job table itself doubles as the persistence layer; APScheduler's
  ``MemoryJobStore`` is used because the durable list is in our table.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from apscheduler.triggers.date import DateTrigger  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import ScheduledEvent
from app.core.event_bus.global_bus import publish_if_available
from app.db import async_session_maker
from app.models import ScheduledJob

logger = logging.getLogger(__name__)


def _row_to_dict(row: ScheduledJob) -> dict[str, object]:
    """Convert a :class:`ScheduledJob` row into a plain dict.

    Used by the agent-facing list/get methods so the ``core/tools``
    layer (which calls them) never has to import ``app.models``.
    Keeps the model boundary clean per the import-linter contract.
    """
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "cron_expression": row.cron_expression,
        "fire_at": row.fire_at,
        "prompt": row.prompt,
        "skill_name": row.skill_name,
        "target_chat_ids": list(row.target_chat_ids or []),
        "target_conversation_id": row.target_conversation_id,
        "working_directory": row.working_directory,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "last_fired_at": getattr(row, "last_fired_at", None),
    }


class JobScheduler:
    """APScheduler wrapper with a Postgres-backed job catalogue."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._running = False

    async def start(self) -> None:
        """Re-hydrate jobs from ``scheduled_jobs`` and start the scheduler."""
        if self._running:
            return
        await self._hydrate_active_jobs()
        self._scheduler.start()
        self._running = True
        logger.info("SCHEDULER_START")

    async def stop(self) -> None:
        """Shut the scheduler down — does NOT fire pending jobs."""
        if not self._running:
            return
        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("SCHEDULER_STOP")

    async def add_job(
        self,
        *,
        session: AsyncSession,
        user_id: uuid.UUID,
        name: str,
        prompt: str,
        cron_expression: str | None = None,
        fire_at: datetime | None = None,
        skill_name: str | None = None,
        target_chat_ids: list[str] | None = None,
        target_conversation_id: uuid.UUID | None = None,
        working_directory: str | None = None,
    ) -> ScheduledJob:
        """Persist a job + register the cron or date trigger atomically.

        Validates the cron expression or fire_at date up front.

        ``target_conversation_id`` is optional; when set, every fire
        persists the agent response into that conversation in addition
        to Telegram fan-out via ``target_chat_ids``.
        """
        # Validate first; we don't want a row that the scheduler can't load.
        if cron_expression:
            trigger = CronTrigger.from_crontab(cron_expression)
        elif fire_at:
            trigger = DateTrigger(run_date=fire_at)
        else:
            raise ValueError("Must provide either cron_expression or fire_at")

        now = datetime.now(UTC)
        row = ScheduledJob(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            cron_expression=cron_expression,
            fire_at=fire_at,
            prompt=prompt,
            skill_name=skill_name,
            target_chat_ids=target_chat_ids or [],
            target_conversation_id=target_conversation_id,
            working_directory=working_directory,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        self._register_with_aps(row, trigger=trigger)
        logger.info(
            "SCHEDULER_JOB_ADDED job_id=%s name=%s cron=%s fire_at=%s",
            row.id,
            name,
            cron_expression,
            fire_at,
        )
        return row

    async def remove_job(
        self,
        *,
        session: AsyncSession,
        job_id: uuid.UUID,
    ) -> bool:
        """Soft-delete the job + remove its APScheduler trigger."""
        row = await session.get(ScheduledJob, job_id)
        if row is None:
            return False
        row.is_active = False
        row.updated_at = datetime.now(UTC)
        await session.commit()
        try:
            self._scheduler.remove_job(str(job_id))
        except Exception:
            logger.debug("SCHEDULER_REMOVE_NOT_REGISTERED job_id=%s", job_id)
        logger.info("SCHEDULER_JOB_REMOVED job_id=%s", job_id)
        return True

    async def list_jobs_for_user(
        self,
        *,
        session: AsyncSession,
        user_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> list[dict[str, object]]:
        """Return scheduled jobs for ``user_id`` as plain dicts.

        Used by the agent-facing ``cron_list`` tool (#313). Returning
        dicts (not ORM rows) keeps the model boundary clean — the
        ``core/tools`` layer does not import ``app.models``.
        """
        stmt = select(ScheduledJob).where(ScheduledJob.user_id == user_id)
        if not include_inactive:
            stmt = stmt.where(ScheduledJob.is_active.is_(True))
        stmt = stmt.order_by(ScheduledJob.created_at.desc())
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        return [_row_to_dict(row) for row in rows]

    async def get_job_for_user(
        self,
        *,
        session: AsyncSession,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> dict[str, object] | None:
        """Return one job iff it exists AND belongs to ``user_id``.

        Used by the agent-facing ``cron_delete`` tool (#313) so the
        tool can authorise without importing ``app.models``.
        """
        row = await session.get(ScheduledJob, job_id)
        if row is None or row.user_id != user_id:
            return None
        return _row_to_dict(row)

    async def _hydrate_active_jobs(self) -> None:
        """Re-register every ``is_active=True`` row at startup."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ScheduledJob).where(ScheduledJob.is_active.is_(True))
            )
            rows = list(result.scalars().all())
        for row in rows:
            try:
                if row.cron_expression:
                    trigger = CronTrigger.from_crontab(row.cron_expression)
                elif row.fire_at:
                    trigger = DateTrigger(run_date=row.fire_at)
                else:
                    raise ValueError("Job has neither cron_expression nor fire_at")
                self._register_with_aps(row, trigger=trigger)
            except Exception:
                logger.exception(
                    "SCHEDULER_HYDRATE_FAILED job_id=%s name=%s cron=%s fire_at=%s",
                    row.id,
                    row.name,
                    row.cron_expression,
                    row.fire_at,
                )
        logger.info("SCHEDULER_HYDRATE count=%d", len(rows))

    def _register_with_aps(self, row: ScheduledJob, *, trigger: CronTrigger | DateTrigger) -> None:
        """Register one job with APScheduler — id matches the DB row's UUID."""
        target_conversation = row.target_conversation_id
        self._scheduler.add_job(
            self._fire_event,
            trigger=trigger,
            id=str(row.id),
            name=row.name,
            replace_existing=True,
            kwargs={
                "job_id": str(row.id),
                "user_id": str(row.user_id),
                "name": row.name,
                "prompt": row.prompt,
                "skill_name": row.skill_name,
                "target_chat_ids": list(row.target_chat_ids or []),
                "target_conversation_id": (
                    str(target_conversation) if target_conversation is not None else None
                ),
                "working_directory": row.working_directory,
            },
        )

    async def _fire_event(
        self,
        *,
        job_id: str,
        user_id: str,
        name: str,
        prompt: str,
        skill_name: str | None,
        target_chat_ids: list[str],
        target_conversation_id: str | None,
        working_directory: str | None,
    ) -> None:
        """APScheduler trigger callback — publishes a ScheduledEvent."""
        event = ScheduledEvent(
            job_id=uuid.UUID(job_id),
            job_name=name,
            prompt=prompt,
            skill_name=skill_name,
            target_chat_ids=target_chat_ids,
            target_conversation_id=(
                uuid.UUID(target_conversation_id) if target_conversation_id else None
            ),
            working_directory=Path(working_directory) if working_directory else None,
            user_id=uuid.UUID(user_id),
        )
        await publish_if_available(event)
        await self._mark_fired(uuid.UUID(job_id))
        logger.info("SCHEDULER_FIRE job_id=%s name=%s", job_id, name)

    @staticmethod
    async def _mark_fired(job_id: uuid.UUID) -> None:
        """Update ``last_fired_at`` on the row."""
        async with async_session_maker() as session:
            row = await session.get(ScheduledJob, job_id)
            if row is None:
                return
            row.last_fired_at = datetime.now(UTC)
            row.last_status = "fired"
            await session.commit()
