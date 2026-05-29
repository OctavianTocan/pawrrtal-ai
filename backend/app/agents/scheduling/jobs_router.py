"""Scheduled-job CRUD API.

Per-user scoped via ``get_allowed_user`` — a user can only see /
modify their own jobs.  Mutate verbs (POST/DELETE) are rejected
with HTTP 503 when the scheduler is disabled (``SCHEDULER_ENABLED=false``);
the GET continues to serve historical rows so the UI doesn't 503
on a flag flip.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.scheduler import JobScheduler
from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.models import ScheduledJob
from app.schemas import ScheduledJobCreate, ScheduledJobRead

logger = logging.getLogger(__name__)


def _get_scheduler(request: Request) -> JobScheduler | None:
    """Pull the live :class:`JobScheduler` off ``app.state``.

    Returns ``None`` when the scheduler is disabled — handlers
    short-circuit on ``None`` instead of raising so the GET path
    can still serve historical rows.
    """
    return getattr(request.app.state, "scheduler", None)


def get_scheduled_jobs_router() -> APIRouter:
    """Build the ``/api/v1/scheduled-jobs`` router."""
    router = APIRouter(prefix="/api/v1/scheduled-jobs", tags=["scheduler"])

    @router.get("/", response_model=list[ScheduledJobRead])
    async def list_jobs(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> list[ScheduledJobRead]:
        """List the calling user's scheduled jobs (active + historical)."""
        result = await session.execute(
            select(ScheduledJob)
            .where(ScheduledJob.user_id == user.id)
            .order_by(ScheduledJob.created_at.desc())
        )
        rows = list(result.scalars().all())
        return [ScheduledJobRead.model_validate(row) for row in rows]

    @router.post("/", response_model=ScheduledJobRead, status_code=201)
    async def create_job(
        payload: ScheduledJobCreate,
        request: Request,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> ScheduledJobRead:
        """Persist + register a new cron job."""
        if not settings.scheduler_enabled:
            raise HTTPException(status_code=503, detail="Scheduler disabled")
        scheduler = _get_scheduler(request)
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not running")
        try:
            row = await scheduler.add_job(
                session=session,
                user_id=user.id,
                name=payload.name,
                cron_expression=payload.cron_expression,
                prompt=payload.prompt,
                skill_name=payload.skill_name,
                target_chat_ids=payload.target_chat_ids,
                target_conversation_id=payload.target_conversation_id,
                working_directory=payload.working_directory,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ScheduledJobRead.model_validate(row)

    @router.delete("/{job_id}", status_code=204)
    async def delete_job(
        job_id: uuid.UUID,
        request: Request,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Soft-delete the job + remove its trigger."""
        # Per-user scope: 404 if the row doesn't exist OR isn't theirs.
        row = await session.get(ScheduledJob, job_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="Job not found")
        scheduler = _get_scheduler(request)
        if scheduler is None:
            # Even with the scheduler off, allow the soft-delete so the
            # row vanishes from the UI.  A future restart with the flag
            # back on will skip it because is_active is False.
            row.is_active = False
            await session.commit()
            return
        await scheduler.remove_job(session=session, job_id=job_id)

    return router
