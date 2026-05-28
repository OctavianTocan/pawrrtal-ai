"""Heartbeat HTTP route — workspace HEARTBEAT.md sync.

POST ``/api/v1/heartbeat/sync`` reads the user's default workspace's
``HEARTBEAT.md``, ensures the heartbeat conversation exists, and
registers one ``scheduled_jobs`` row per check. From there, the
existing JobScheduler → EventBus → AgentHandler → NotificationService
pipeline does all the work — cron fires, the agent runs the prompt,
the response lands in the heartbeat conversation (web) and, when the
user has linked Telegram, in their Telegram chat.

The sync is intentionally not run automatically. The user edits the
file in their workspace, then triggers this endpoint (or the
Settings UI does it for them). That keeps the file-on-disk the
single source of truth and avoids a watcher that fights edits.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.scheduler import JobScheduler
from app.crud import channel as channel_crud
from app.crud.heartbeat import sync_workspace_heartbeats
from app.crud.workspace import get_default_workspace
from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session

logger = logging.getLogger(__name__)


class HeartbeatSyncResponse(BaseModel):
    """Result of a successful ``POST /api/v1/heartbeat/sync``."""

    workspace_id: str
    conversation_id: str
    jobs_created: int
    jobs_removed: int
    telegram_linked: bool


def get_heartbeat_router() -> APIRouter:
    """Build the heartbeat router (mounted at ``/api/v1/heartbeat``)."""
    router = APIRouter(prefix="/api/v1/heartbeat", tags=["heartbeat"])

    @router.post("/sync", response_model=HeartbeatSyncResponse)
    async def sync_heartbeats(
        request: Request,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> HeartbeatSyncResponse:
        """Re-register the user's HEARTBEAT.md as scheduled jobs.

        Returns 503 when the scheduler is disabled — the persisted
        rows would never fire, so we'd rather surface the misconfig
        than silently accept work.
        """
        if not settings.scheduler_enabled:
            raise HTTPException(status_code=503, detail="Scheduler disabled")
        scheduler = _get_scheduler(request)
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not running")
        workspace = await get_default_workspace(user.id, session)
        if workspace is None:
            raise HTTPException(
                status_code=409,
                detail="No default workspace; finish onboarding first.",
            )
        binding = await channel_crud.get_binding(
            user_id=user.id, provider="telegram", session=session
        )
        telegram_chat_id = binding.external_chat_id if binding is not None else None

        result = await sync_workspace_heartbeats(
            session=session,
            user_id=user.id,
            workspace=workspace,
            scheduler=scheduler,
            telegram_chat_id=telegram_chat_id,
        )
        return HeartbeatSyncResponse(
            workspace_id=str(result.workspace_id),
            conversation_id=str(result.conversation_id),
            jobs_created=result.jobs_created,
            jobs_removed=result.jobs_removed,
            telegram_linked=telegram_chat_id is not None,
        )

    return router


def _get_scheduler(request: Request) -> JobScheduler | None:
    """Pull the live JobScheduler off ``app.state``.

    Mirrors ``app.api.scheduled_jobs._get_scheduler`` — the scheduler
    lifespan stashes the instance there when ``SCHEDULER_ENABLED=true``.
    Returns ``None`` so the handler can 503 with a clean message
    instead of crashing on a missing attribute.
    """
    return getattr(request.app.state, "scheduler", None)
