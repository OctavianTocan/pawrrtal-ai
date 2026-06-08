"""Heartbeat sync helper for workspace HEARTBEAT.md scheduled jobs."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.scheduling import HeartbeatCheck, load_heartbeat_md
from app.conversations.crud import get_or_create_heartbeat_conversation
from app.governance_models import ScheduledJob

if TYPE_CHECKING:
    from app.agents.scheduling import JobScheduler
    from app.models import Workspace

logger = logging.getLogger(__name__)

# Job-name prefix that lets the sync helper recognise (and replace) its
# own rows without disturbing user-authored scheduled jobs in the same
# table. The full name is ``heartbeat:<workspace_id>:<check_name>``.
JOB_NAME_PREFIX = "heartbeat:"


@dataclass(frozen=True)
class SyncResult:
    """Outcome of one ``sync_workspace_heartbeats`` call."""

    workspace_id: uuid.UUID
    conversation_id: uuid.UUID
    jobs_created: int
    jobs_removed: int


async def sync_workspace_heartbeats(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    workspace: Workspace,
    scheduler: JobScheduler,
    telegram_chat_id: str | None = None,
) -> SyncResult:
    """Re-register a workspace's HEARTBEAT.md as scheduled-job rows.

    Reads ``<workspace.path>/HEARTBEAT.md``, ensures the user has a
    heartbeat conversation to receive the responses, and registers
    one ``scheduled_jobs`` row per check (replacing any existing rows
    that this workspace previously synced).

    ``telegram_chat_id`` is the user's linked Telegram chat. When set,
    every heartbeat job also targets that chat. When the user has not
    linked Telegram, jobs run web-only.

    Idempotent: re-running picks up the latest HEARTBEAT.md, removes
    job rows whose ``name`` is no longer in the file, and replaces
    cron / prompt edits on the rows that survived. Active rows from
    other surfaces (the user's own POST /api/v1/scheduled-jobs jobs)
    are untouched.
    """
    path = Path(workspace.path) / "HEARTBEAT.md"
    config = load_heartbeat_md(path)

    conversation = await get_or_create_heartbeat_conversation(user_id, session)

    workspace_prefix = f"{JOB_NAME_PREFIX}{workspace.id}:"
    desired_names = {f"{workspace_prefix}{check.name}" for check in config.checks}
    target_chats = [telegram_chat_id] if telegram_chat_id else []

    removed = await _remove_stale_jobs(
        session=session,
        scheduler=scheduler,
        workspace_prefix=workspace_prefix,
        keep_names=desired_names,
    )

    created = 0
    for check in config.checks:
        await _add_or_replace_job(
            session=session,
            scheduler=scheduler,
            user_id=user_id,
            workspace=workspace,
            check=check,
            workspace_prefix=workspace_prefix,
            target_chat_ids=target_chats,
            target_conversation_id=conversation.id,
        )
        created += 1

    await session.commit()
    logger.info(
        "HEARTBEAT_SYNC workspace_id=%s checks=%d removed=%d",
        workspace.id,
        created,
        removed,
    )
    return SyncResult(
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        jobs_created=created,
        jobs_removed=removed,
    )


async def _remove_stale_jobs(
    *,
    session: AsyncSession,
    scheduler: JobScheduler,
    workspace_prefix: str,
    keep_names: set[str],
) -> int:
    """Soft-delete heartbeat job rows for this workspace not in ``keep_names``."""
    stmt = select(ScheduledJob).where(
        ScheduledJob.name.startswith(workspace_prefix),
        ScheduledJob.is_active.is_(True),
    )
    result = await session.execute(stmt)
    removed = 0
    for row in result.scalars():
        if row.name in keep_names:
            continue
        await scheduler.remove_job(session=session, job_id=row.id)
        removed += 1
    return removed


async def _add_or_replace_job(
    *,
    session: AsyncSession,
    scheduler: JobScheduler,
    user_id: uuid.UUID,
    workspace: Workspace,
    check: HeartbeatCheck,
    workspace_prefix: str,
    target_chat_ids: list[str],
    target_conversation_id: uuid.UUID,
) -> None:
    """Insert a new job row or replace the existing one in place."""
    job_name = f"{workspace_prefix}{check.name}"
    existing = await session.execute(select(ScheduledJob).where(ScheduledJob.name == job_name))
    existing_row = existing.scalar_one_or_none()
    if existing_row is not None:
        # Soft-delete the old row first so the scheduler de-registers
        # it; the fresh add_job re-registers with the new cron/prompt.
        await scheduler.remove_job(session=session, job_id=existing_row.id)

    await scheduler.add_job(
        session=session,
        user_id=user_id,
        name=job_name,
        cron_expression=check.cron,
        prompt=check.prompt,
        target_chat_ids=target_chat_ids,
        target_conversation_id=target_conversation_id,
        working_directory=workspace.path,
    )
