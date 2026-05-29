"""Audit log query API.

Per-user read-only views over the ``audit_events`` table. Writes go
through :class:`app.core.governance.audit.AuditLogger` and never
through this router.

Routes
------
* ``GET /api/v1/audit``            — paginated list, newest first.
* ``GET /api/v1/audit/summary``    — 24h dashboard aggregate.

Both routes are scoped to the authenticated user via
:func:`app.users.get_allowed_user`; a user can never see another
user's events. Admin / cross-user views are not in this PR's scope.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.governance.audit.crud import (
    DEFAULT_DASHBOARD_WINDOW_HOURS,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    get_user_activity_summary,
    list_audit_events_for_user,
)
from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.schemas import AuditEventRead

# Upper bound on the dashboard window so the aggregation query can't
# scan the whole table. 90 days matches the default retention.
MAX_DASHBOARD_WINDOW_HOURS = 90 * 24


def get_audit_router() -> APIRouter:
    """Build the audit-log router mounted at ``/api/v1/audit``."""
    router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

    @router.get("/", response_model=list[AuditEventRead])
    async def list_audit(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
        limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
        offset: int = Query(default=0, ge=0),
        event_type: str | None = Query(default=None),
        since: datetime | None = Query(default=None),
    ) -> list[AuditEventRead]:
        """Return the most-recent audit events for the calling user.

        Filterable by ``event_type`` and a ``since`` timestamp. When
        the audit log is globally disabled the route serves an empty
        list instead of 404 so the UI can render the same panel
        without conditionals — historical rows from before the
        disable are intentionally still visible.
        """
        if not settings.audit_log_enabled:
            return []
        rows = await list_audit_events_for_user(
            user_id=user.id,
            session=session,
            limit=limit,
            offset=offset,
            event_type=event_type,
            since=since,
        )
        return [AuditEventRead.model_validate(row) for row in rows]

    @router.get("/summary")
    async def audit_summary(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
        hours: int = Query(
            default=DEFAULT_DASHBOARD_WINDOW_HOURS,
            ge=1,
            le=MAX_DASHBOARD_WINDOW_HOURS,
        ),
    ) -> dict[str, Any]:
        """Aggregate audit dashboard for the calling user.

        Returns event counts by type + risk level over the requested
        window. ``hours`` is bounded so the query stays cheap.
        """
        if not settings.audit_log_enabled:
            raise HTTPException(status_code=404, detail="Audit log disabled")
        return await get_user_activity_summary(
            user_id=user.id,
            session=session,
            hours=hours,
        )

    return router
